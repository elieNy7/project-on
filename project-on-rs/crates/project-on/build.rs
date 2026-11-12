//! L'icône et la fiche de l'exécutable Windows : le logo de Project-On dans l'Explorateur, la
//! barre des tâches et le raccourci du Bureau (comme Pgraphics).

fn main() {
    println!("cargo:rerun-if-changed=../../../assets/logo.ico");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() != Ok("windows") {
        return;
    }
    let mut res = winresource::WindowsResource::new();
    res.set_icon("../../../assets/logo.ico")
        .set("ProductName", "Project-On")
        .set("FileDescription", "Project-On — projection pour églises")
        .set("CompanyName", "ParaTech Sarl")
        .set("LegalCopyright", "© ParaTech Sarl");
    // Sans le compilateur de ressources du SDK Windows, l'exécutable marche, sans son icône.
    if let Err(e) = res.compile() {
        println!("cargo:warning=icône de l'exécutable non intégrée : {e}");
    }
}
