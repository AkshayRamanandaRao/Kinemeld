use std::{env, path::PathBuf, process::Command};

fn main() {
    println!("cargo:rerun-if-changed=src/gui_test_macos.m");
    if env::var("CARGO_CFG_TARGET_OS").as_deref() != Ok("macos") { return; }
    let output = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    let object = output.join("gui_test_macos.o");
    let status = Command::new("clang").args(["-fobjc-arc", "-mmacosx-version-min=11.0", "-c", "src/gui_test_macos.m", "-o"]).arg(&object).status().expect("macOS GUI-test driver needs the system clang");
    assert!(status.success(), "Could not compile macOS GUI-test driver");
    assert!(Command::new("ar").arg("rcs").arg(output.join("libkinemeld_gui_test.a")).arg(&object).status().unwrap().success());
    println!("cargo:rustc-link-search=native={}", output.display());
    println!("cargo:rustc-link-lib=static=kinemeld_gui_test");
    println!("cargo:rustc-link-lib=framework=AppKit");
}
