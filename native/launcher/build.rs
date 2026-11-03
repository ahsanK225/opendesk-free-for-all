fn main() {
    println!("cargo:rerun-if-env-changed=OPENDESK_RESOURCE_RES");
    if let Some(value) = std::env::var_os("OPENDESK_RESOURCE_RES") {
        let path = std::path::PathBuf::from(value);
        assert!(
            path.is_absolute() && path.is_file(),
            "The compiled Windows resource is missing"
        );
        println!("cargo:rerun-if-changed={}", path.display());
        println!("cargo:rustc-link-arg-bins={}", path.display());
    }
}
