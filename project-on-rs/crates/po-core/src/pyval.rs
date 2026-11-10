//! Les conversions de Python sur une valeur JSON (`bool()`, `str()`, `int()`, `float()`,
//! `round()`, `min()`, `max()`) : un réglage écrit à la main ou par une ancienne version se lit
//! exactement comme dans la 2.8.

use serde_json::Value;

/// `bool(v)`.
pub fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().is_some_and(|f| f != 0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

fn is_space(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

/// `repr(f)` d'un nombre à virgule : le plus court qui se relit à l'identique, `12.0`, `1e+16`,
/// `1.5e-05`.
pub fn float_repr(f: f64) -> String {
    if f.is_nan() {
        return "nan".into();
    }
    if f.is_infinite() {
        return if f > 0.0 { "inf".into() } else { "-inf".into() };
    }
    // « 1.2345e3 » : les chiffres les plus courts et l'exposant.
    let sci = format!("{f:e}");
    let (mantissa, exponent) = sci.split_once('e').unwrap_or((&sci, "0"));
    let exponent: i32 = exponent.parse().unwrap_or(0);
    let negative = mantissa.starts_with('-');
    let digits: String = mantissa.chars().filter(char::is_ascii_digit).collect();
    let sign = if negative { "-" } else { "" };
    if (-4..16).contains(&exponent) {
        let point = exponent + 1; // position de la virgule dans les chiffres
        let body = if point <= 0 {
            format!("0.{}{digits}", "0".repeat(point.unsigned_abs() as usize))
        } else if point as usize >= digits.len() {
            format!("{digits}{}.0", "0".repeat(point as usize - digits.len()))
        } else {
            format!("{}.{}", &digits[..point as usize], &digits[point as usize..])
        };
        format!("{sign}{body}")
    } else {
        let mantissa = if digits.len() > 1 { format!("{}.{}", &digits[..1], &digits[1..]) } else { digits };
        let exp_sign = if exponent < 0 { '-' } else { '+' };
        format!("{sign}{mantissa}e{exp_sign}{:02}", exponent.unsigned_abs())
    }
}

fn repr_str(s: &str) -> String {
    let quote = if s.contains('\'') && !s.contains('"') { '"' } else { '\'' };
    let mut out = String::with_capacity(s.len() + 2);
    out.push(quote);
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if (c as u32) < 0x20 || (0x7f..0xa0).contains(&(c as u32)) => {
                out.push_str(&format!("\\x{:02x}", c as u32))
            }
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

fn repr(v: &Value) -> String {
    match v {
        Value::String(s) => repr_str(s),
        other => to_str(other),
    }
}

/// `str(v)` : `True`, `12`, `12.5`, `['a', 1]`, `{'a': None}`…
pub fn to_str(v: &Value) -> String {
    match v {
        Value::Null => "None".into(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        Value::Number(n) => match (n.as_i64(), n.as_u64()) {
            (Some(i), _) => i.to_string(),
            (None, Some(u)) => u.to_string(),
            _ => float_repr(n.as_f64().unwrap_or(0.0)),
        },
        Value::String(s) => s.clone(),
        Value::Array(items) => format!("[{}]", items.iter().map(repr).collect::<Vec<_>>().join(", ")),
        Value::Object(map) => {
            format!(
                "{{{}}}",
                map.iter().map(|(k, v)| format!("{}: {}", repr_str(k), repr(v))).collect::<Vec<_>>().join(", ")
            )
        }
    }
}

/// Les chiffres d'un nombre écrit en texte, avec les `_` que Python admet entre deux chiffres.
fn without_underscores(s: &str) -> Option<String> {
    if !s.contains('_') {
        return Some(s.to_string());
    }
    let chars: Vec<char> = s.chars().collect();
    for (i, &c) in chars.iter().enumerate() {
        if c == '_' {
            let before = i.checked_sub(1).and_then(|j| chars.get(j)).is_some_and(char::is_ascii_digit);
            let after = chars.get(i + 1).is_some_and(char::is_ascii_digit);
            if !before || !after {
                return None;
            }
        }
    }
    Some(s.replace('_', ""))
}

/// `int(v)` ; `None` là où Python lève `ValueError` ou `TypeError`.
pub fn to_int(v: &Value) -> Option<i64> {
    match v {
        Value::Bool(b) => Some(i64::from(*b)),
        Value::Number(n) => n
            .as_i64()
            .or_else(|| n.as_u64().map(|u| i64::try_from(u).unwrap_or(i64::MAX)))
            .or_else(|| n.as_f64().filter(|f| f.is_finite()).map(|f| f.trunc() as i64)),
        Value::String(s) => {
            let text = without_underscores(s.trim_matches(is_space))?;
            let digits = text.strip_prefix(['+', '-']).unwrap_or(&text);
            if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
                return None;
            }
            text.parse::<i64>().ok().or_else(|| Some(if text.starts_with('-') { i64::MIN } else { i64::MAX }))
        }
        Value::Null | Value::Array(_) | Value::Object(_) => None,
    }
}

/// `float(v)` ; `None` là où Python lève `ValueError` ou `TypeError`.
pub fn to_float(v: &Value) -> Option<f64> {
    match v {
        Value::Bool(b) => Some(f64::from(u8::from(*b))),
        Value::Number(n) => n.as_f64(),
        Value::String(s) => {
            let text = without_underscores(s.trim_matches(is_space))?;
            let body = text.strip_prefix(['+', '-']).unwrap_or(&text).to_ascii_lowercase();
            let special = matches!(body.as_str(), "inf" | "infinity" | "nan");
            let numeric = !body.is_empty()
                && body.chars().all(|c| c.is_ascii_digit() || matches!(c, '.' | 'e' | '+' | '-'))
                && body.chars().any(|c| c.is_ascii_digit());
            if !special && !numeric {
                return None;
            }
            text.parse::<f64>().ok()
        }
        Value::Null | Value::Array(_) | Value::Object(_) => None,
    }
}

/// `round(f)` : à l'entier pair le plus proche en cas d'égalité (« arrondi du banquier »).
pub fn round_half_even(f: f64) -> f64 {
    f.round_ties_even()
}

/// `min(a, b)` de Python : `b` seulement s'il est strictement plus petit (un NaN ne gagne jamais).
pub fn py_min<T: PartialOrd>(a: T, b: T) -> T {
    if b < a { b } else { a }
}

/// `max(a, b)` de Python : `b` seulement s'il est strictement plus grand.
pub fn py_max<T: PartialOrd>(a: T, b: T) -> T {
    if b > a { b } else { a }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    // Valeurs attendues données par Python 3.14.
    #[test]
    fn python_str() {
        assert_eq!(to_str(&json!(true)), "True");
        assert_eq!(to_str(&json!(12.0)), "12.0");
        assert_eq!(to_str(&json!(1e16)), "1e+16");
        assert_eq!(to_str(&json!(0.0001)), "0.0001");
        assert_eq!(to_str(&json!(0.00001)), "1e-05");
        assert_eq!(to_str(&json!(123456.789)), "123456.789");
        assert_eq!(to_str(&json!(["a", 1, null, "l'a"])), r#"['a', 1, None, "l'a"]"#);
        assert_eq!(to_str(&json!({"a": false})), "{'a': False}");
    }

    #[test]
    fn python_numbers() {
        assert_eq!(to_int(&json!(" 12 ")), Some(12));
        assert_eq!(to_int(&json!("1_000")), Some(1000));
        assert_eq!(to_int(&json!("12.5")), None);
        assert_eq!(to_int(&json!(-12.9)), Some(-12));
        assert_eq!(to_int(&json!(true)), Some(1));
        assert_eq!(to_int(&json!([1])), None);
        assert_eq!(to_float(&json!(" 1.5e2 ")), Some(150.0));
        assert_eq!(to_float(&json!("abc")), None);
        assert!(to_float(&json!("-inf")).is_some_and(|f| f == f64::NEG_INFINITY));
        assert_eq!(round_half_even(2.5), 2.0);
        assert_eq!(round_half_even(3.5), 4.0);
        assert!(py_max(1.0, py_min(2.0, f64::NAN)) == 2.0);
    }
}
