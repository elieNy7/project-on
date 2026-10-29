//! Extension SQLite chargeable : `unaccent()` native, sans passer par Python.
//!
//! En fonction Python, chaque ligne coûte la création d'une chaîne Python
//! (les paragraphes de sermons sont longs) : 8 s pour 568 000 paragraphes,
//! même avec le pliage en Rust. Enregistrée directement dans SQLite, elle lit
//! le texte UTF-8 de la ligne sur place.
//!
//! Chargée par `app.database.connection` avec
//! `conn.load_extension(<chemin du .pyd>, entrypoint="sqlite3_projectoncore_init")`.

use std::os::raw::{c_char, c_int};

use rusqlite::functions::{Context, FunctionFlags};
use rusqlite::types::ValueRef;
use rusqlite::{Connection, Result, ffi};

use crate::fold;

/// Point d'entrée appelé par SQLite (`sqlite3_load_extension`).
///
/// # Safety
/// Appelée par SQLite avec des pointeurs valides.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn sqlite3_projectoncore_init(
    db: *mut ffi::sqlite3,
    pz_err_msg: *mut *mut c_char,
    p_api: *mut ffi::sqlite3_api_routines,
) -> c_int {
    unsafe { Connection::extension_init2(db, pz_err_msg, p_api, register) }
}

fn register(db: Connection) -> Result<bool> {
    db.create_scalar_function(
        c"unaccent",
        1,
        FunctionFlags::SQLITE_UTF8
            | FunctionFlags::SQLITE_DETERMINISTIC
            | FunctionFlags::SQLITE_INNOCUOUS,
        unaccent_sql,
    )?;
    // false : propre à cette connexion, comme `create_function` en Python.
    Ok(false)
}

/// Mêmes règles que `unaccent()` en Python appelée par SQLite : NULL, 0 et
/// "" donnent "" ; un nombre est d'abord converti en texte.
fn unaccent_sql(ctx: &Context<'_>) -> Result<String> {
    Ok(match ctx.get_raw(0) {
        ValueRef::Null => String::new(),
        ValueRef::Text(bytes) => fold(&String::from_utf8_lossy(bytes)),
        ValueRef::Integer(0) => String::new(),
        ValueRef::Integer(i) => i.to_string(),
        ValueRef::Real(0.0) => String::new(),
        ValueRef::Real(f) => fold(&f.to_string()),
        ValueRef::Blob([]) => String::new(),
        ValueRef::Blob(b) => fold(&String::from_utf8_lossy(b)),
    })
}
