// Own-process GUI automation; no Accessibility permission or replacement dialog result.
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
        for (NSWindow *window in NSApp.windows) [windows addObject:@{@"title": window.title ?: @"", @"class": NSStringFromClass(window.class), @"visible": @(window.visible), @"modal": @(window == NSApp.modalWindow), @"firstResponder": NSStringFromClass(window.firstResponder.class) ?: @""}];
        result[@"windows"] = windows;
    }
    [self write:@"action-result.json" value:result];
}
- (void)record:(NSDictionary *)action window:(NSWindow *)window {
    [self.events addObject:@{@"action": action, @"window": window.title ?: @"", @"class": NSStringFromClass(window.class), @"pid": @(NSProcessInfo.processInfo.processIdentifier)}];
    // Captures the app's own panel. Remote file-service subviews may be excluded by AppKit.
    NSView *view = window.contentView;
    NSBitmapImageRep *bitmap = [view bitmapImageRepForCachingDisplayInRect:view.bounds];
    if (bitmap) {
        [view cacheDisplayInRect:view.bounds toBitmapImageRep:bitmap];
        NSString *name = [NSString stringWithFormat:@"native-%@-%lu.png", self.plan[@"id"], (unsigned long)self.index];
        [[bitmap representationUsingType:NSBitmapImageFileTypePNG properties:@{}] writeToFile:[self.root stringByAppendingPathComponent:name] atomically:YES];
    }
}
- (NSButton *)button:(NSView *)view titles:(NSArray *)titles {
    if ([view isKindOfClass:NSButton.class] && [titles containsObject:((NSButton *)view).title] && ((NSButton *)view).enabled) return (NSButton *)view;
    for (NSView *child in view.subviews) { NSButton *found = [self button:child titles:titles]; if (found) return found; }
    return nil;
}
- (void)key:(NSString *)characters code:(unsigned short)code flags:(NSEventModifierFlags)flags window:(NSWindow *)window {
    NSEvent *event = [NSEvent keyEventWithType:NSEventTypeKeyDown location:NSZeroPoint modifierFlags:flags timestamp:NSProcessInfo.processInfo.systemUptime windowNumber:window.windowNumber context:nil characters:characters charactersIgnoringModifiers:characters isARepeat:NO keyCode:code];
    [NSApp sendEvent:event];
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
    if (NSProcessInfo.processInfo.systemUptime - self.since > 35) { [self result:@"Timed out locating the app's native control"]; return; }
    NSDictionary *action = self.plan[@"actions"][self.index];
    NSString *kind = action[@"kind"];
    NSWindow *hostModal = NSApp.modalWindow;
    NSWindow *modal = hostModal;
    if ([kind isEqual:@"button"]) while (modal.attachedSheet) modal = modal.attachedSheet;
    if ([kind isEqual:@"close"]) {
        if (modal) return;
        for (NSWindow *window in NSApp.windows) if ([window.title isEqual:@"Kinemeld"] && window.visible) {
            [self record:action window:window]; self.index++; self.stage = 0; self.since = NSProcessInfo.processInfo.systemUptime; [self result:nil]; [window performClose:nil]; return;
        }
        return;
    }
    if (self.stage == 3 && ([kind isEqual:@"open"] || [kind isEqual:@"save"] || [kind isEqual:@"cancel"])) {
        NSWindow *panel = [NSApp windowWithWindowNumber:self.panelNumber];
        NSWindow *top = hostModal;
        while (top.attachedSheet) top = top.attachedSheet;
        BOOL overwrite = [kind isEqual:@"save"] && top && [self button:top.contentView titles:@[@"Replace", @"Replace File"]];
        if (!panel || !panel.visible || overwrite) {
            self.index++; self.stage = 0; self.since = NSProcessInfo.processInfo.systemUptime; [self result:nil];
        }
        return;
    }
    if (!modal) return;
    if ([kind isEqual:@"button"]) {
        if ([modal isKindOfClass:NSSavePanel.class]) return;
        NSArray *titles = [action[@"text"] isEqual:@"refuse-overwrite"] ? @[@"Cancel", @"Don't Replace", @"No"] : @[action[@"text"]];
        NSButton *button = [self button:modal.contentView titles:titles];
        if (!button) return;
        [self record:action window:modal]; self.index++; self.stage = 0; self.since = NSProcessInfo.processInfo.systemUptime; [self result:nil]; [button performClick:nil]; return;
    }
    if (![modal isKindOfClass:NSSavePanel.class]) return;
    NSSavePanel *panel = (NSSavePanel *)modal;
    BOOL opening = [panel isKindOfClass:NSOpenPanel.class];
    if ([kind isEqual:@"cancel"]) {
        if (([action[@"dialog"] isEqual:@"open"] && !opening) || ([action[@"dialog"] isEqual:@"save"] && opening)) return;
        [self record:action window:panel]; self.panelNumber = panel.windowNumber; self.stage = 3; self.since = NSProcessInfo.processInfo.systemUptime;
        [self key:@"\033" code:53 flags:0 window:panel]; return;
    }
    if (![kind isEqual:(opening ? @"open" : @"save")]) return;
    NSString *path = action[@"path"];
    if (self.stage == 0) {
        self.panelNumber = panel.windowNumber;
        [self record:action window:panel]; [panel makeKeyAndOrderFront:nil]; [NSApp activateIgnoringOtherApps:YES];
        if (opening) {
            // Open's selection is made through its real Go to Folder field and native Return.
            [self key:@"G" code:5 flags:NSEventModifierFlagCommand | NSEventModifierFlagShift window:panel];
        } else {
            panel.directoryURL = [NSURL fileURLWithPath:path.stringByDeletingLastPathComponent isDirectory:YES];
            panel.nameFieldStringValue = path.lastPathComponent;
        }
        self.stage = 1; self.since = NSProcessInfo.processInfo.systemUptime; return;
    }
    if (NSProcessInfo.processInfo.systemUptime - self.since < 0.6) return;
    if (opening && self.stage == 1) {
        NSWindow *key = NSApp.keyWindow ?: panel;
        [NSApp sendAction:@selector(selectAll:) to:nil from:nil];
        for (NSUInteger i = 0; i < path.length; i++) [self key:[path substringWithRange:NSMakeRange(i, 1)] code:0 flags:0 window:key];
        [self key:@"\r" code:36 flags:0 window:key];
        self.stage = 2; self.since = NSProcessInfo.processInfo.systemUptime; return;
    }
    self.stage = 3; self.since = NSProcessInfo.processInfo.systemUptime;
    [self key:@"\r" code:36 flags:0 window:panel];
}
@end

void kinemeld_gui_test_start(const char *root) {
    static KinemeldGuiTest *driver;
    driver = [KinemeldGuiTest new]; driver.root = [NSString stringWithUTF8String:root];
    [driver write:@"mac-driver.json" value:@{@"started": @YES, @"pid": @(NSProcessInfo.processInfo.processIdentifier)}];
    NSTimer *timer = [NSTimer timerWithTimeInterval:0.1 target:driver selector:@selector(tick:) userInfo:nil repeats:YES];
    [NSRunLoop.mainRunLoop addTimer:timer forMode:NSDefaultRunLoopMode];
    [NSRunLoop.mainRunLoop addTimer:timer forMode:NSModalPanelRunLoopMode];
    [NSRunLoop.mainRunLoop addTimer:timer forMode:NSRunLoopCommonModes];
}
