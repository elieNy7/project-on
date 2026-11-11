//! Les lignes d'un PDF dans l'ordre de lecture : `cargo run -p po-pdf --example lignes -- <pdf> [début] [fin]`.
fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let Some(pdf) = args.first() else { return };
    let pages = po_pdf::pages(std::path::Path::new(pdf)).unwrap_or_default();
    let lines = po_pdf::ordered_lines(&pages);
    let from: usize = args.get(1).and_then(|a| a.parse().ok()).unwrap_or(0);
    let to: usize = args.get(2).and_then(|a| a.parse().ok()).unwrap_or(lines.len());
    for line in lines.iter().take(to).skip(from) {
        println!("{line}");
    }
}
