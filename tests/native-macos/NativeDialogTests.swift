import AppKit
import XCTest

@MainActor
final class NativeDialogTests: XCTestCase {
    private var root = URL(fileURLWithPath: "/")
    private var phase = ""
    private var pid: pid_t = 0
    private var app: XCUIApplication!
    private var events: [[String: Any]] = []
    private var planID: Any = 0

    private func read(_ name: String) -> [String: Any]? {
        guard let data = try? Data(contentsOf: root.appendingPathComponent(name)) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }
    private func write(_ name: String, _ value: [String: Any]) throws {
        try JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys])
            .write(to: root.appendingPathComponent(name), options: .atomic)
    }
    private func wait(_ label: String, timeout: TimeInterval = 20, _ condition: () -> Bool) throws {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return }
            RunLoop.current.run(until: Date().addingTimeInterval(0.1))
        }
        throw NSError(domain: "NativeDialogs", code: 1, userInfo: [NSLocalizedDescriptionKey: "Timed out: \(label)"])
    }
    private func button(_ names: [String], in scope: XCUIElement) -> XCUIElement? {
        let nativeIDs = ["Cancel": "CancelButton", "Open": "OKButton", "Save": "OKButton"]
        for name in names {
            for identifier in [name, nativeIDs[name]].compactMap({ $0 }) {
                for control in scope.descendants(matching: .button).matching(identifier: identifier).allElementsBoundByIndex {
                    if control.exists && control.isEnabled && control.isHittable { return control }
                }
            }
        }
        return nil
    }
    private func attachDiagnostics(_ name: String) -> (String, Data) {
        let tree = String(app.debugDescription.prefix(1_000_000))
        print("NATIVE_UI_TREE \(name)\n\(tree)")
        let description = XCTAttachment(string: tree); description.name = name + "-tree"; description.lifetime = .keepAlways; add(description)
        let image = app.screenshot()
        let screenshot = XCTAttachment(screenshot: image); screenshot.name = name + "-screenshot"; screenshot.lifetime = .keepAlways; add(screenshot)
        return (tree, image.pngRepresentation)
    }
    private func evidence(_ action: [String: Any], _ control: XCUIElement, index: Int) throws {
        let prefix = "xcui-\(String(describing: planID))-\(index)-\(events.count)"
        let (tree, image) = attachDiagnostics(prefix)
        try image.write(to: root.appendingPathComponent(prefix + ".png"))
        try tree.write(to: root.appendingPathComponent(prefix + ".txt"), atomically: true, encoding: .utf8)
        events.append(["action": action, "pid": pid, "driver": "XCUITest", "label": control.label,
                       "identifier": control.identifier, "enabled": control.isEnabled, "hittable": control.isHittable,
                       "screenshot": prefix + ".png"])
    }
    private func picker(_ opening: Bool) throws -> XCUIElement {
        let title = opening ? "Open" : "Save"
        var picker: XCUIElement?
        try wait("native \(title) picker") {
            let candidates = self.app.descendants(matching: .dialog).allElementsBoundByIndex
                + self.app.descendants(matching: .sheet).allElementsBoundByIndex
                + self.app.windows.allElementsBoundByIndex
            picker = candidates.first {
                $0.descendants(matching: .button).matching(identifier: "OKButton").firstMatch.exists
                    && self.button(["Cancel"], in: $0) != nil
                    && $0.popUpButtons.matching(identifier: "where popup").firstMatch.exists
            }
            return picker != nil
        }
        return picker!
    }
    private func overwriteSheet() -> XCUIElement? {
        let candidates = app.descendants(matching: .sheet).allElementsBoundByIndex
            + app.descendants(matching: .dialog).allElementsBoundByIndex
            + app.descendants(matching: .alert).allElementsBoundByIndex
        return candidates.filter { self.button(["Replace", "Replace File"], in: $0) != nil }
            .min { $0.frame.width * $0.frame.height < $1.frame.width * $1.frame.height }
    }
    private func fill(_ field: XCUIElement, text: String, directory: Bool = false) throws {
        try wait("native editable text field") { field.exists && field.isEnabled && field.isHittable }
        field.click()
        field.typeKey("a", modifierFlags: [.command])
        field.typeKey(XCUIKeyboardKey.delete, modifierFlags: [])
        try waitValue(field, text: "")
        field.typeText(text)
        try waitValue(field, text: text, directory: directory)
    }
    private func waitValue(_ field: XCUIElement, text: String, directory: Bool = false) throws {
        do { try wait("native text readback") {
            guard let value = field.value as? String else { return false }
            return value == text || (directory && text.hasSuffix("/") && value == String(text.dropLast()))
        } }
        catch {
            throw NSError(domain: "NativeDialogs", code: 5, userInfo: [NSLocalizedDescriptionKey:
                "Native text readback mismatch for \(field.identifier): expected \(text.debugDescription), observed \(String(describing: field.value))"])
        }
    }
    private func choose(_ action: [String: Any], next: [String: Any]?, index: Int) throws {
        let opening = action["kind"] as? String == "open"
        let path = try XCTUnwrap(action["path"] as? String)
        let destination = URL(fileURLWithPath: path).standardizedFileURL
        XCTAssertTrue(destination.path.hasPrefix(root.path + "/"), "Native picker target escaped the marked root")
        let panel = try picker(opening)
        try evidence(action, panel, index: index)
        panel.typeKey("g", modifierFlags: [.command, .shift])
        let sheet = panel.sheets.firstMatch
        try wait("native Go to Folder sheet") { sheet.exists }
        let combo = sheet.comboBoxes.firstMatch
        let field = combo.exists ? combo : sheet.textFields.firstMatch
        let goPath = opening ? destination.path : destination.deletingLastPathComponent().path + "/"
        try fill(field, text: goPath, directory: !opening)
        try evidence(action, sheet, index: index)
        field.typeKey(XCUIKeyboardKey.return, modifierFlags: [])
        try wait("Go to Folder sheet closes") { !sheet.exists }
        if !opening {
            let named = panel.textFields.matching(NSPredicate(format: "label IN %@", ["Save As:", "Save As", "Name:", "Name"])).firstMatch
            try fill(named.exists ? named : panel.textFields.firstMatch, text: destination.lastPathComponent)
        }
        if panel.exists {
            var accept: XCUIElement?
            try wait("enabled native \(opening ? "Open" : "Save") button") {
                accept = self.button([opening ? "Open" : "Save"], in: panel); return accept != nil
            }
            try evidence(action, accept!, index: index)
            accept!.click()
        }
        if next?["text"] as? String == "refuse-overwrite" {
            try wait("actual enabled Replace confirmation") { self.overwriteSheet() != nil }
            try evidence(action, overwriteSheet()!, index: index)
        } else { try wait("native picker returns") { !panel.exists } }
    }
    private func perform(_ action: [String: Any], next: [String: Any]?, index: Int) throws {
        switch action["kind"] as? String {
        case "open", "save": try choose(action, next: next, index: index)
        case "cancel":
            let panel = try picker(action["dialog"] as? String == "open")
            var cancel: XCUIElement?
            try wait("enabled native Cancel button") { cancel = self.button(["Cancel"], in: panel); return cancel != nil }
            try evidence(action, cancel!, index: index); cancel!.click()
            try wait("cancelled native picker closes") { !panel.exists }
        case "button":
            let text = try XCTUnwrap(action["text"] as? String)
            if text == "refuse-overwrite" {
                try wait("actual Replace confirmation before refusal") { self.overwriteSheet() != nil }
                let sheet = overwriteSheet()!
                let cancel = try XCTUnwrap(button(["Cancel", "Don't Replace", "No"], in: sheet))
                try evidence(action, sheet, index: index); cancel.click()
                try wait("Replace confirmation dismissed") { self.overwriteSheet() == nil }
                _ = try picker(false)
            } else {
                var control: XCUIElement?
                try wait("actual native \(text) button") { control = self.button([text], in: self.app); return control != nil }
                try evidence(action, control!, index: index); control!.click()
            }
        case "close":
            let close = app.windows["Kinemeld"].buttons[XCUIIdentifierCloseWindow]
            try wait("actual window close button") { close.exists && close.isEnabled && close.isHittable }
            try evidence(action, close, index: index); close.click()
        default: throw NSError(domain: "NativeDialogs", code: 2, userInfo: [NSLocalizedDescriptionKey: "Unknown native action"])
        }
    }
    func testNativeDialogs() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        root = URL(fileURLWithPath: try XCTUnwrap(env["KINEMELD_GUI_ROOT"])).standardizedFileURL.resolvingSymlinksInPath()
        phase = try XCTUnwrap(env["KINEMELD_GUI_PHASE"])
        pid = try XCTUnwrap(Int32(try XCTUnwrap(env["KINEMELD_GUI_PID"])))
        let executable = URL(fileURLWithPath: try XCTUnwrap(env["KINEMELD_GUI_EXECUTABLE"])).resolvingSymlinksInPath()
        XCTAssertTrue(FileManager.default.fileExists(atPath: root.appendingPathComponent(".kinemeld-native-gui-test").path))
        let marker = try XCTUnwrap(read("mac-driver.json"))
        XCTAssertEqual(marker["phase"] as? String, phase)
        XCTAssertEqual(marker["root"] as? String, root.path)
        XCTAssertEqual((marker["pid"] as? NSNumber)?.int32Value, pid)
        let bundleID = try XCTUnwrap(env["KINEMELD_GUI_BUNDLE_ID"])
        let running = NSRunningApplication.runningApplications(withBundleIdentifier: bundleID)
        guard running.count == 1, let owned = running.first, owned.processIdentifier == pid,
              owned.executableURL?.resolvingSymlinksInPath() == executable else {
            throw NSError(domain: "NativeDialogs", code: 4, userInfo: [NSLocalizedDescriptionKey: "XCTest requires the one already supervised packaged process; refusing ambiguous or different applications"])
        }
        app = XCUIApplication(bundleIdentifier: bundleID)
        XCTAssertNotEqual(app.state, .notRunning)
        app.activate() // Preserve the existing LaunchServices instance and its isolated configuration.
        XCTAssertFalse(owned.isTerminated)
        var lastID = ""
        do {
            let deadline = Date().addingTimeInterval(900)
            while Date() < deadline {
                let viewer = read("viewer-report.json")
                let goal = phase == "initial" ? "crash-ready" : "close-ready"
                if owned.isTerminated {
                    XCTAssertEqual(viewer?["status"] as? String, goal, "Native process exited before its required GUI cases")
                    try write("xcui-\(phase).json", ["status": "complete", "phase": phase, "pid": pid])
                    return
                }
                if let plan = read("action.json"), let actions = plan["actions"] as? [[String: Any]] {
                    planID = plan["id"] ?? 0
                    let key = String(describing: planID)
                    if key != lastID {
                        events = []
                        for index in actions.indices {
                            try perform(actions[index], next: index + 1 < actions.count ? actions[index + 1] : nil, index: index)
                            try write("action-result.json", ["id": planID, "done": index == actions.count - 1, "events": events])
                        }
                        lastID = key
                    }
                }
                RunLoop.current.run(until: Date().addingTimeInterval(0.1))
            }
            throw NSError(domain: "NativeDialogs", code: 3, userInfo: [NSLocalizedDescriptionKey: "Native XCTest session exceeded 15 minutes"])
        } catch {
            let original = error
            print("NATIVE_UI_FAILURE \(original)")
            let (tree, image) = attachDiagnostics("failure-" + phase)
            do {
                try tree.write(to: root.appendingPathComponent("xcui-failure-\(phase).txt"), atomically: true, encoding: .utf8)
                try image.write(to: root.appendingPathComponent("xcui-failure-\(phase).png"))
                try write("action-result.json", ["id": planID, "done": false, "events": events, "error": String(describing: original)])
            } catch {
                print("NATIVE_UI_DIAGNOSTIC_WRITE_FAILED \(error)")
                XCTFail("Native XCTest diagnostics could not be saved: \(error)")
            }
            throw original
        }
    }
}
