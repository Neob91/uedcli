//! Argument parsing for `brush build cube`, backed by clap. Handled: --width --breadth --height
//! --at --base-name --csg --solidity. Anything else (an unrecognized flag, a value clap can't
//! parse, -h/--help, --project) fails to parse and this falls through to the `old/bin/uedcli`
//! proxy unchanged -- see dev/epics/refactor.md's subprocess-strangler section.
//!
//! Not handled -- always proxies: --prop, --texture, --mover-class, --rotate, --folder, --label.

use clap::Parser;
use rust_decimal::Decimal;
use std::str::FromStr;

use crate::brush::builders::base::{CsgOperation, Solidity};
use crate::brush::builders::cube::build_cube;

#[derive(Parser)]
#[command(disable_help_flag = true)]
struct CubeArgs {
    #[arg(long, allow_hyphen_values = true)]
    width: f64,
    #[arg(long, allow_hyphen_values = true)]
    breadth: f64,
    #[arg(long, allow_hyphen_values = true)]
    height: f64,
    #[arg(long, allow_hyphen_values = true, value_parser = parse_at)]
    at: Option<(Decimal, Decimal, Decimal)>,
    #[arg(long, value_parser = parse_base_name)]
    base_name: Option<String>,
    #[arg(long, value_enum)]
    csg: Option<CsgOperation>,
    #[arg(long, value_enum)]
    solidity: Option<Solidity>,
}

// clap treats a bare "-" as a value, not a flag -- old/bin/uedcli's own argparse does too, but
// then fails downstream needing a project this verb's native path never requires. Rejecting it
// here keeps that case proxying to old/bin/uedcli instead of silently succeeding where it fails.
fn parse_base_name(text: &str) -> Result<String, String> {
    if text == "-" {
        return Err("bare \"-\" is not a valid base name".to_string());
    }
    Ok(text.to_string())
}

// Rejects anything but digits/dot/sign per comma-separated part -- in particular scientific
// notation ("-1e5,0,0"), which Decimal::from_str would otherwise happily accept as a number that
// old/bin/uedcli's own parser refuses.
fn parse_at(text: &str) -> Result<(Decimal, Decimal, Decimal), String> {
    let parts: Vec<&str> = text.split(',').map(str::trim).collect();
    if parts.len() != 3 {
        return Err(format!("expected 3 comma-separated numbers, got {text}"));
    }
    let mut values = Vec::with_capacity(3);
    for part in &parts {
        let digits = part.strip_prefix(['-', '+']).unwrap_or(part);
        if digits.is_empty() || !digits.chars().all(|c| c.is_ascii_digit() || c == '.') {
            return Err(format!("not a plain decimal number: {part}"));
        }
        values.push(Decimal::from_str(part).map_err(|_| format!("not a number: {part}"))?);
    }
    Ok((values[0], values[1], values[2]))
}

pub fn try_build_cube(args: &[String]) -> Option<Result<String, String>> {
    if args.len() < 3 || args[0] != "brush" || args[1] != "build" || args[2] != "cube" {
        return None;
    }
    let rest = args[3..].iter().cloned();
    let parsed = CubeArgs::try_parse_from(std::iter::once("cube".to_string()).chain(rest)).ok()?;

    Some(build_cube(
        parsed.width,
        parsed.breadth,
        parsed.height,
        parsed.at.unwrap_or((Decimal::ZERO, Decimal::ZERO, Decimal::ZERO)),
        parsed.base_name.unwrap_or_else(|| "Cube".to_string()),
        parsed.csg.unwrap_or(CsgOperation::Add),
        parsed.solidity.unwrap_or(Solidity::Solid),
    ))
}
