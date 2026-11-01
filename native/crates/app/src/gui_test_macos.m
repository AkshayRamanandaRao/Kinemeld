// Explicit GUI-test instrumentation. Only the application's own windows receive events.
#import <AppKit/AppKit.h>

@interface KinemeldGuiTest : NSObject
@property(nonatomic, strong) NSString *root;
@property(nonatomic, strong) NSDictionary *plan;
@property(nonatomic, strong) NSMutableArray *events;
@property NSUInteger index;
@property NSInteger stage;
@property NSInteger panelNumber;
@property NSTimeInterval since;
@property BOOL ticking;
@end

@implementation KinemeldGuiTest
- (void)write:(NSString *)name value:(id)value {
    NSData *data = [NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingPrettyPrinted error:nil];
    [data writeToFile:[self.root stringByAppendingPathComponent:name] options:NSDataWritingAtomic error:nil];
}
- (void)result:(NSString *)error {
    NSMutableDictionary *result = [@{@"id": self.plan[@"id"], @"done": @(self.index >= [self.plan[@"actions"] count]), @"events": self.events} mutableCopy];
    if (error) {
        result[@"error"] = error;
        NSMutableArray *windows = [NSMutableArray array];
        for (NSWindow *window in NSApp.windows) [windows addObject:@{@"title": window.title ?: @"", @"class": NSStringFromClass(window.class), @"visible": @(window.visible), @"modal": @(window == NSApp.modalWindow), @"key": @(window == NSApp.keyWindow), @"firstResponder": NSStringFromClass(window.firstResponder.class) ?: @""}];
        result[@"windows"] = windows;
        result[@"stage"] = @(self.stage);
    }
    [self write:@"action-result.json" value:result];
}
- (void)record:(NSDictionary *)action window:(NSWindow *)window {
    [self.events addObject:@{@"action": action, @"window": window.title ?: @"", @"class": NSStringFromClass(window.class), @"pid": @(NSProcessInfo.processInfo.processIdentifier), @"windowNumber": @(window.windowNumber), @"firstResponder": NSStringFromClass(window.firstResponder.class) ?: @""}];
    // AppKit can exclude the remote file-service subviews from this own-window capture.
    NSView *view = window.contentView;
    NSBitmapImageRep *bitmap = [view bitmapImageRepForCachingDisplayInRect:view.bounds];
    if (bitmap) {
        [view cacheDisplayInRect:view.bounds toBitmapImageRep:bitmap];
        NSString *name = [NSString stringWithFormat:@"native-%@-%lu.png", self.plan[@"id"], (unsigned long)self.index];
        [[bitmap representationUsingType:NSBitmapImageFileTypePNG properties:@{}] writeToFile:[self.root stringByAppendingPathComponent:name] atomically:YES];
    }
}
- (NSButton *)button:(NSView *)view titles:(NSArray *)titles {
    if (!view || view.hiddenOrHasHiddenAncestor || view.alphaValue <= 0) return nil;
    if ([view isKindOfClass:NSButton.class] && [titles containsObject:((NSButton *)view).title] && ((NSButton *)view).enabled) return (NSButton *)view;
    for (NSView *child in view.subviews) { NSButton *found = [self button:child titles:titles]; if (found) return found; }
    return nil;
}
- (NSWindow *)overwriteConfirmation {
    NSWindow *window = NSApp.modalWindow;
    while (window.attachedSheet.visible) window = window.attachedSheet;
    return window.visible && [self button:window.contentView titles:@[@"Replace", @"Replace File"]] ? window : nil;
}
- (void)click:(id)target selector:(SEL)selector {
    [target performSelector:selector withObject:nil afterDelay:0.01 inModes:@[NSDefaultRunLoopMode, NSModalPanelRunLoopMode]];
}
- (NSWindow *)inputWindow:(NSWindow *)panel {
    if (!panel.visible || ![NSApp.windows containsObject:panel]) return nil;
    NSWindow *target = panel;
    while (target.attachedSheet.visible) target = target.attachedSheet;
    if (NSApp.modalWindow != panel && NSApp.modalWindow != target) return nil;
    if (![NSApp.windows containsObject:target]) return nil;
    [NSApp activateIgnoringOtherApps:YES]; [target makeKeyAndOrderFront:nil];
    return NSApp.keyWindow == target ? target : nil;
}
- (void)key:(NSString *)characters code:(unsigned short)code modifiers:(NSEventModifierFlags)modifiers window:(NSWindow *)window {
    for (NSNumber *type in @[@(NSEventTypeKeyDown), @(NSEventTypeKeyUp)]) {
        NSEvent *event = [NSEvent keyEventWithType:type.unsignedIntegerValue location:NSZeroPoint modifierFlags:modifiers timestamp:NSProcessInfo.processInfo.systemUptime windowNumber:window.windowNumber context:nil characters:characters charactersIgnoringModifiers:characters isARepeat:NO keyCode:code];
        [NSApp sendEvent:event];
    }
}
- (void)type:(NSString *)text window:(NSWindow *)window {
    [self key:@"a" code:0 modifiers:NSEventModifierFlagCommand window:window];
    for (NSUInteger index = 0; index < text.length;) {
        NSRange range = [text rangeOfComposedCharacterSequenceAtIndex:index];
        [self key:[text substringWithRange:range] code:0 modifiers:0 window:window];
        index = NSMaxRange(range);
    }
    [self.events addObject:@{@"input": @"native key events", @"text": text, @"windowNumber": @(window.windowNumber)}];
}
- (void)sendInput:(NSDictionary *)input {
    if (![input[@"plan"] isEqual:self.plan[@"id"]] || [input[@"index"] unsignedIntegerValue] != self.index) return;
    NSWindow *window = input[@"window"];
    if (!window.visible || ![NSApp.windows containsObject:window] || NSApp.keyWindow != window) { [self result:@"The native input window lost its owned key-window identity"]; return; }
    NSString *kind = input[@"kind"];
    if ([kind isEqual:@"navigate"]) {
        if (![input[@"opening"] boolValue]) [self type:[input[@"path"] lastPathComponent] window:window];
        [self key:@"G" code:5 modifiers:NSEventModifierFlagCommand | NSEventModifierFlagShift window:window];
        [self.events addObject:@{@"input": @"Go to Folder shortcut", @"windowNumber": @(window.windowNumber)}];
    } else {
        if ([kind isEqual:@"path"]) [self type:input[@"path"] window:window];
        [self key:[kind isEqual:@"cancel"] ? @"\033" : @"\r" code:[kind isEqual:@"cancel"] ? 53 : 36 modifiers:0 window:window];
        [self.events addObject:@{@"input": kind, @"windowNumber": @(window.windowNumber)}];
    }
}
- (void)queueInput:(NSString *)kind path:(NSString *)path opening:(BOOL)opening window:(NSWindow *)window {
    // A default button may start another modal loop. Let the driver timer continue there.
    NSDictionary *input = @{@"kind": kind, @"path": path ?: @"", @"opening": @(opening), @"window": window, @"plan": self.plan[@"id"], @"index": @(self.index)};
    [self performSelector:@selector(sendInput:) withObject:input afterDelay:0.01 inModes:@[NSDefaultRunLoopMode, NSModalPanelRunLoopMode]];
}
- (void)finishAction {
    self.index++; self.stage = 0; self.since = NSProcessInfo.processInfo.systemUptime; [self result:nil];
}
- (void)tick:(NSTimer *)timer {
    if (self.ticking) return;
    self.ticking = YES;
    @try { [self advance]; }
    @catch (NSException *error) { if (self.plan) [self result:error.reason ?: @"AppKit GUI driver exception"]; }
    @finally { self.ticking = NO; }
}
- (void)advance {
    NSData *bytes = [NSData dataWithContentsOfFile:[self.root stringByAppendingPathComponent:@"action.json"]];
    NSDictionary *plan = bytes ? [NSJSONSerialization JSONObjectWithData:bytes options:0 error:nil] : nil;
    if (!plan || ![plan[@"actions"] isKindOfClass:NSArray.class]) return;
    if (![self.plan[@"id"] isEqual:plan[@"id"]]) { self.plan = plan; self.index = 0; self.stage = 0; self.events = [NSMutableArray array]; self.since = NSProcessInfo.processInfo.systemUptime; }
    if (self.index >= [self.plan[@"actions"] count]) return;
    if (NSProcessInfo.processInfo.systemUptime - self.since > 35) { [self result:@"Timed out operating the app's native dialog"]; return; }
    NSDictionary *action = self.plan[@"actions"][self.index];
    NSString *kind = action[@"kind"];
    NSWindow *modal = NSApp.modalWindow;
    if ([kind isEqual:@"close"]) {
        if (modal) return;
        for (NSWindow *window in NSApp.windows) if ([window.title isEqual:@"Kinemeld"] && window.visible) {
            [self record:action window:window]; [self finishAction]; [self click:window selector:@selector(performClose:)]; return;
        }
        return;
    }
    if ([kind isEqual:@"button"]) {
        if ([action[@"text"] isEqual:@"refuse-overwrite"]) {
            NSWindow *panel = [NSApp windowWithWindowNumber:self.panelNumber];
            if (!panel || !panel.visible || ![panel isKindOfClass:NSSavePanel.class]) { [self result:@"The Save panel closed before overwrite refusal"]; return; }
            if (self.stage == 0) {
                NSWindow *confirmation = [self overwriteConfirmation]; if (!confirmation) return;
                NSButton *cancel = [self button:confirmation.contentView titles:@[@"Cancel", @"Don't Replace", @"No"]]; if (!cancel) return;
                [self record:action window:confirmation]; [self click:cancel selector:@selector(performClick:)];
                self.stage = 5; self.since = NSProcessInfo.processInfo.systemUptime; return;
            }
            if (NSProcessInfo.processInfo.systemUptime - self.since < 0.8) return;
            if (!panel.visible) { [self result:@"Overwrite refusal closed the Save panel instead of retaining it"]; return; }
            if ([self overwriteConfirmation]) return;
            [self.events addObject:@{@"nativeState": @"Save panel retained after refusing the observed Replace confirmation"}];
            [self finishAction]; return;
        }
        if (!modal) return;
        while (modal.attachedSheet.visible) modal = modal.attachedSheet;
        NSButton *button = [self button:modal.contentView titles:@[action[@"text"]]];
        if (!button) return;
        [self record:action window:modal]; [self finishAction]; [self click:button selector:@selector(performClick:)]; return;
    }
    NSWindow *priorPanel = self.panelNumber ? [NSApp windowWithWindowNumber:self.panelNumber] : nil;
    if (self.stage == 3 && (!priorPanel || !priorPanel.visible)) { [self finishAction]; return; }
    if (self.stage == 4) {
        if (!priorPanel || !priorPanel.visible) { [self finishAction]; return; }
        BOOL refusalNext = self.index + 1 < [self.plan[@"actions"] count] && [self.plan[@"actions"][self.index + 1][@"text"] isEqual:@"refuse-overwrite"];
        if ([kind isEqual:@"save"] && refusalNext && NSProcessInfo.processInfo.systemUptime - self.since >= 0.8) {
            if (![NSFileManager.defaultManager fileExistsAtPath:action[@"path"]]) { [self result:@"Overwrite refusal requires an actually existing target"]; return; }
            NSWindow *confirmation = [self overwriteConfirmation]; if (!confirmation) return;
            [self record:action window:confirmation];
            [self.events addObject:@{@"nativeState": @"Observed enabled native Replace confirmation for an existing target"}];
            [self finishAction]; return;
        }
        return; // Wait for the one issued action; never resend Cancel/Escape while closing.
    }
    if (![modal isKindOfClass:NSSavePanel.class]) return;
    BOOL opening = [modal isKindOfClass:NSOpenPanel.class];
    if ([kind isEqual:@"cancel"]) {
        if (([action[@"dialog"] isEqual:@"open"] && !opening) || ([action[@"dialog"] isEqual:@"save"] && opening)) return;
        NSWindow *target = [self inputWindow:modal]; if (!target) return;
        [self record:action window:target]; self.panelNumber = modal.windowNumber;
        self.stage = 4; self.since = NSProcessInfo.processInfo.systemUptime;
        [self queueInput:@"cancel" path:nil opening:opening window:target]; return;
    }
    if (![kind isEqual:(opening ? @"open" : @"save")]) return;
    if (self.stage == 0) {
        self.panelNumber = modal.windowNumber; self.stage = 1; self.since = NSProcessInfo.processInfo.systemUptime; return;
    }
    if (NSProcessInfo.processInfo.systemUptime - self.since < 0.8) return;
    NSWindow *target = [self inputWindow:modal]; if (!target) return;
    NSString *path = action[@"path"];
    if (self.stage == 1) {
        [self record:action window:target];
        self.stage = 2; self.since = NSProcessInfo.processInfo.systemUptime;
        [self queueInput:@"navigate" path:path opening:opening window:target]; return;
    }
    if (self.stage == 2) {
        self.stage = 3; self.since = NSProcessInfo.processInfo.systemUptime;
        [self queueInput:@"path" path:opening ? path : path.stringByDeletingLastPathComponent opening:opening window:target]; return;
    }
    if (self.stage == 3) {
        if (modal.attachedSheet.visible) return;
        self.stage = 4; self.since = NSProcessInfo.processInfo.systemUptime;
        [self queueInput:opening ? @"native Open default action" : @"native Save default action" path:nil opening:opening window:target];
    }
}
@end

void kinemeld_gui_test_start(const char *root) {
    static KinemeldGuiTest *driver;
    driver = [KinemeldGuiTest new]; driver.root = [NSString stringWithUTF8String:root];
    NSData *bytes = [NSData dataWithContentsOfFile:[driver.root stringByAppendingPathComponent:@"config.json"]];
    NSDictionary *config = bytes ? [NSJSONSerialization JSONObjectWithData:bytes options:0 error:nil] : nil;
    [driver write:@"mac-driver.json" value:@{@"started": @YES, @"root": driver.root, @"phase": config[@"phase"] ?: @"", @"pid": @(NSProcessInfo.processInfo.processIdentifier), @"bundle": NSBundle.mainBundle.bundlePath}];
    NSTimer *timer = [NSTimer timerWithTimeInterval:0.1 target:driver selector:@selector(tick:) userInfo:nil repeats:YES];
    [NSRunLoop.mainRunLoop addTimer:timer forMode:NSDefaultRunLoopMode];
    [NSRunLoop.mainRunLoop addTimer:timer forMode:NSModalPanelRunLoopMode];
    [NSRunLoop.mainRunLoop addTimer:timer forMode:NSRunLoopCommonModes];
}
