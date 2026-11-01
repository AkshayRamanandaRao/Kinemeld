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
        result[@"stage"] = @(self.stage);
        result[@"accessibility"] = [self accessibilitySnapshot:NSApp.modalWindow];
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
- (id)attribute:(NSString *)name item:(id)item {
    // Remote panel proxies can expose the public key-based API instead of modern accessors.
    if ([item respondsToSelector:@selector(accessibilityAttributeNames)] && [item respondsToSelector:@selector(accessibilityAttributeValue:)]) {
        @try { if ([[item accessibilityAttributeNames] containsObject:name]) return [item accessibilityAttributeValue:name]; }
        @catch (NSException *error) { /* A closing remote control is no longer readable. */ }
    }
    return nil;
}
- (NSString *)role:(id)item {
    NSString *role = [item respondsToSelector:@selector(accessibilityRole)] ? [(id<NSAccessibility>)item accessibilityRole] : nil;
    return role.length ? role : [self attribute:NSAccessibilityRoleAttribute item:item];
}
- (id)value:(id)item {
    id value = [item respondsToSelector:@selector(accessibilityValue)] ? [(id<NSAccessibility>)item accessibilityValue] : nil;
    if (!value || ([value isKindOfClass:NSString.class] && ![(NSString *)value length])) return [self attribute:NSAccessibilityValueAttribute item:item] ?: value;
    return value;
}
- (NSArray *)accessibles:(id)root {
    if (!root) return @[];
    NSMutableArray *queue = [NSMutableArray arrayWithObject:root], *found = [NSMutableArray array];
    NSMutableSet *seen = [NSMutableSet set];
    while (queue.count && found.count < 512) {
        id item = queue.firstObject; [queue removeObjectAtIndex:0];
        NSValue *identity = [NSValue valueWithNonretainedObject:item];
        if ([seen containsObject:identity]) continue;
        [seen addObject:identity]; [found addObject:item];
        @try {
            NSArray *children = [item respondsToSelector:@selector(accessibilityChildren)] ? [(id<NSAccessibility>)item accessibilityChildren] : nil;
            if (!children.count) children = [self attribute:NSAccessibilityChildrenAttribute item:item];
            if ([children isKindOfClass:NSArray.class]) [queue addObjectsFromArray:children];
        } @catch (NSException *error) { /* A closing remote view can invalidate its children. */ }
    }
    return found;
}
- (NSString *)accessibleTitle:(id)item {
    NSString *title = [item respondsToSelector:@selector(accessibilityTitle)] ? [(id<NSAccessibility>)item accessibilityTitle] : nil;
    if (title.length) return title;
    NSString *label = [item respondsToSelector:@selector(accessibilityLabel)] ? [(id<NSAccessibility>)item accessibilityLabel] : nil;
    if (label.length) return label;
    for (NSString *name in @[NSAccessibilityTitleAttribute, NSAccessibilityDescriptionAttribute]) {
        NSString *text = [self attribute:name item:item];
        if ([text isKindOfClass:NSString.class] && text.length) return text;
    }
    id value = [self value:item];
    if ([value isKindOfClass:NSString.class]) return value;
    return @"";
}
- (id)accessibleButton:(id)root titles:(NSArray *)titles {
    for (id item in [self accessibles:root]) {
        if (![[self role:item] isEqual:NSAccessibilityButtonRole]) continue;
        if (![titles containsObject:[self accessibleTitle:item]]) continue;
        NSNumber *enabled = [self attribute:NSAccessibilityEnabledAttribute item:item];
        BOOL isEnabled = enabled ? enabled.boolValue : ([item respondsToSelector:@selector(isAccessibilityEnabled)] && [(id<NSAccessibility>)item isAccessibilityEnabled]);
        if (!isEnabled) continue;
        BOOL legacyPress = [item respondsToSelector:@selector(accessibilityActionNames)] && [[item accessibilityActionNames] containsObject:NSAccessibilityPressAction];
        if ([item respondsToSelector:@selector(accessibilityPerformPress)] || legacyPress) return item;
    }
    return nil;
}
- (NSArray *)accessibilitySnapshot:(id)root {
    NSMutableArray *result = [NSMutableArray array];
    for (id item in [self accessibles:root]) {
        @try {
            NSString *role = [self role:item];
            [result addObject:@{@"class": NSStringFromClass([item class]), @"role": role ?: @"", @"title": [self accessibleTitle:item]}];
        } @catch (NSException *error) { /* Retain the surviving native controls. */ }
    }
    return result;
}
- (BOOL)selectFile:(NSString *)path panel:(NSOpenPanel *)panel {
    for (id item in [self accessibles:panel]) {
        if (![[self role:item] isEqual:NSAccessibilityRowRole]) continue;
        BOOL matching = NO;
        for (id child in [self accessibles:item]) if ([[self accessibleTitle:child] isEqual:path.lastPathComponent]) { matching = YES; break; }
        if (matching && [item respondsToSelector:@selector(accessibilityIsAttributeSettable:)] && [item accessibilityIsAttributeSettable:NSAccessibilitySelectedAttribute]) {
            [item accessibilitySetValue:@YES forAttribute:NSAccessibilitySelectedAttribute]; return YES;
        }
        if (matching && [item respondsToSelector:@selector(setAccessibilitySelected:)]) { [(id<NSAccessibility>)item setAccessibilitySelected:YES]; return YES; }
    }
    return NO;
}
- (BOOL)fillText:(NSString *)text root:(id)root matching:(NSString *)current {
    for (id item in [self accessibles:root]) {
        if (![[self role:item] isEqual:NSAccessibilityTextFieldRole]) continue;
        id value = [self value:item];
        if (current && ![value isEqual:current]) continue;
        if ([item respondsToSelector:@selector(accessibilityIsAttributeSettable:)] && [item accessibilityIsAttributeSettable:NSAccessibilityValueAttribute]) {
            [item accessibilitySetValue:text forAttribute:NSAccessibilityValueAttribute];
        } else if ([item respondsToSelector:@selector(setAccessibilityValue:)]) {
            [(id<NSAccessibility>)item setAccessibilityValue:text];
        } else continue;
        if ([[self value:item] isEqual:text]) return YES;
    }
    return NO;
}
- (id)goSheet:(NSWindow *)panel {
    if (panel.attachedSheet.visible) return panel.attachedSheet;
    for (id item in [self accessibles:panel]) if ([[self role:item] isEqual:NSAccessibilitySheetRole]) return item;
    return nil;
}
- (BOOL)fillSaveName:(NSString *)name panel:(NSWindow *)panel {
    for (id item in [self accessibles:panel]) {
        if (![[self role:item] isEqual:NSAccessibilityTextFieldRole]) continue;
        NSString *label = [self accessibleTitle:item];
        id titleElement = [self attribute:NSAccessibilityTitleUIElementAttribute item:item];
        NSString *relatedLabel = titleElement ? [self accessibleTitle:titleElement] : @"";
        NSArray *labels = @[@"Save As:", @"Save As", @"Name:", @"Name"];
        if (![labels containsObject:label] && ![labels containsObject:relatedLabel]) continue;
        return [self fillText:name root:item matching:nil];
    }
    return NO;
}
- (void)goToFolder:(NSWindow *)window {
    // Deliver the real shortcut only to this application's native dialog window.
    if (NSApp.keyWindow != window || NSApp.modalWindow != window) { [self result:@"The native file panel is not the app's key modal window"]; return; }
    for (NSNumber *type in @[@(NSEventTypeKeyDown), @(NSEventTypeKeyUp)]) {
        NSEvent *event = [NSEvent keyEventWithType:type.unsignedIntegerValue location:NSZeroPoint modifierFlags:NSEventModifierFlagCommand | NSEventModifierFlagShift timestamp:NSProcessInfo.processInfo.systemUptime windowNumber:window.windowNumber context:nil characters:@"G" charactersIgnoringModifiers:@"G" isARepeat:NO keyCode:5];
        [NSApp sendEvent:event];
    }
}
- (void)pressAccessible:(id)button {
    if ([button respondsToSelector:@selector(accessibilityPerformPress)] && [(id<NSAccessibility>)button accessibilityPerformPress]) return;
    if ([button respondsToSelector:@selector(accessibilityActionNames)] && [[button accessibilityActionNames] containsObject:NSAccessibilityPressAction]) {
        [button accessibilityPerformAction:NSAccessibilityPressAction]; return;
    }
    [self result:@"The native accessibility button rejected its press"];
}
- (void)click:(id)target selector:(SEL)selector {
    // Defer UI actions so a nested native modal loop can continue the driver timer.
    [target performSelector:selector withObject:nil afterDelay:0.01 inModes:@[NSDefaultRunLoopMode, NSModalPanelRunLoopMode]];
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
            [self record:action window:window]; self.index++; self.stage = 0; self.since = NSProcessInfo.processInfo.systemUptime; [self result:nil]; [self click:window selector:@selector(performClose:)]; return;
        }
        return;
    }
    if (self.stage == 3 && ([kind isEqual:@"open"] || [kind isEqual:@"save"] || [kind isEqual:@"cancel"])) {
        NSWindow *panel = [NSApp windowWithWindowNumber:self.panelNumber];
        NSWindow *top = hostModal;
        while (top.attachedSheet) top = top.attachedSheet;
        BOOL overwrite = [kind isEqual:@"save"] && top && ([self button:top.contentView titles:@[@"Replace", @"Replace File"]] || [self accessibleButton:top titles:@[@"Replace", @"Replace File"]]);
        if (!panel || !panel.visible || overwrite) {
            self.index++; self.stage = 0; self.since = NSProcessInfo.processInfo.systemUptime; [self result:nil];
        }
        return;
    }
    if (!modal) return;
    if ([kind isEqual:@"button"]) {
        NSArray *titles = [action[@"text"] isEqual:@"refuse-overwrite"] ? @[@"Cancel", @"Don't Replace", @"No"] : @[action[@"text"]];
        if ([modal isKindOfClass:NSSavePanel.class] && (![action[@"text"] isEqual:@"refuse-overwrite"] || ![self accessibleButton:modal titles:@[@"Replace", @"Replace File"]])) return;
        NSButton *button = [self button:modal.contentView titles:titles];
        id accessible = button ? nil : [self accessibleButton:modal titles:titles];
        if (!button && !accessible) return;
        [self record:action window:modal]; self.index++; self.stage = 0; self.since = NSProcessInfo.processInfo.systemUptime; [self result:nil];
        if (button) [self click:button selector:@selector(performClick:)];
        else [self performSelector:@selector(pressAccessible:) withObject:accessible afterDelay:0.01 inModes:@[NSDefaultRunLoopMode, NSModalPanelRunLoopMode]];
        return;
    }
    if (![modal isKindOfClass:NSSavePanel.class]) return;
    NSSavePanel *panel = (NSSavePanel *)modal;
    BOOL opening = [panel isKindOfClass:NSOpenPanel.class];
    if ([kind isEqual:@"cancel"]) {
        if (([action[@"dialog"] isEqual:@"open"] && !opening) || ([action[@"dialog"] isEqual:@"save"] && opening)) return;
        [self record:action window:panel]; self.panelNumber = panel.windowNumber; self.stage = 3; self.since = NSProcessInfo.processInfo.systemUptime;
        [self click:panel selector:@selector(cancel:)]; return;
    }
    if (![kind isEqual:(opening ? @"open" : @"save")]) return;
    NSString *path = action[@"path"];
    if (self.stage == 0) {
        // A visible shell can precede the remote service. Wait for a real enabled control.
        if (![self button:panel.contentView titles:@[@"Cancel"]] && ![self accessibleButton:panel titles:@[@"Cancel"]]) return;
        self.panelNumber = panel.windowNumber;
        [self record:action window:panel]; [panel makeKeyAndOrderFront:nil]; [NSApp activateIgnoringOtherApps:YES];
        // directoryURL/nameField setters are configuration-only. Operate the running UI instead.
        [self performSelector:@selector(goToFolder:) withObject:panel afterDelay:0.01 inModes:@[NSDefaultRunLoopMode, NSModalPanelRunLoopMode]];
        self.stage = 1; self.since = NSProcessInfo.processInfo.systemUptime; return;
    }
    if (NSProcessInfo.processInfo.systemUptime - self.since < 0.6) return;
    if (self.stage == 1) {
        id sheet = [self goSheet:panel];
        if (!sheet) return;
        NSString *destination = opening ? path : path.stringByDeletingLastPathComponent;
        if (![self fillText:destination root:sheet matching:nil]) return;
        NSButton *go = [sheet isKindOfClass:NSWindow.class] ? [self button:((NSWindow *)sheet).contentView titles:@[@"Go"]] : nil;
        id accessible = go ? nil : [self accessibleButton:sheet titles:@[@"Go"]];
        if (!go && !accessible) return;
        [self.events addObject:@{@"action": action, @"nativeText": destination, @"nativeControl": @"Go to Folder"}];
        self.stage = 2; self.since = NSProcessInfo.processInfo.systemUptime;
        if (go) [self click:go selector:@selector(performClick:)];
        else [self performSelector:@selector(pressAccessible:) withObject:accessible afterDelay:0.01 inModes:@[NSDefaultRunLoopMode, NSModalPanelRunLoopMode]];
        return;
    }
    if ([self goSheet:panel]) return;
    BOOL selected = opening && [self selectFile:path panel:(NSOpenPanel *)panel];
    if (!opening && ![self fillSaveName:path.lastPathComponent panel:panel]) return;
    NSButton *button = [self button:panel.contentView titles:(opening ? @[@"Open"] : @[@"Save"])];
    id accessible = button ? nil : [self accessibleButton:panel titles:(opening ? @[@"Open"] : @[@"Save"])];
    if (!button && !accessible) return;
    // The selected RFD path and resulting files are checked only after the real modal returns.
    [self.events addObject:@{@"action": action, @"nativeControl": opening ? @"Open" : @"Save", @"selectedAccessibleRow": @(selected)}];
    [self record:action window:panel]; self.stage = 3; self.since = NSProcessInfo.processInfo.systemUptime;
    if (button) [self click:button selector:@selector(performClick:)];
    else if (accessible) [self performSelector:@selector(pressAccessible:) withObject:accessible afterDelay:0.01 inModes:@[NSDefaultRunLoopMode, NSModalPanelRunLoopMode]];
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
