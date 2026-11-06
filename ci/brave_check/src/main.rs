//! Validate a filter list with the real Brave engine (brave/adblock-rust).
//!
//! usage: brave_check <list.txt> [max_failed]
//!
//! Fails (exit 1) when
//!   * a rule produced by our converter (`:style(...)`, `:remove()`) is rejected
//!     by adblock-rust, or
//!   * the total number of rejected rules exceeds `max_failed` (default 250),
//!     which catches upstream syntax regressions.
//!
//! Rules that use uBO-only syntax (regex hostnames, `$domain=/re/`, `$denyallow`,
//! `$replace`, `##^`, ...) are expected to be rejected and are only counted.

use adblock::lists::{parse_filter, ParseOptions, ParsedLine, RuleTypes};
use std::io::BufRead;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!("usage: brave_check <list.txt> [max_failed]");
        std::process::exit(2);
    }
    let path = &args[1];
    let max_failed: usize = args
        .get(2)
        .and_then(|s| s.parse().ok())
        .or_else(|| std::env::var("MAX_FAILED").ok().and_then(|s| s.parse().ok()))
        .unwrap_or(250);

    let file = std::fs::File::open(path).expect("open list");
    let opts = ParseOptions {
        rule_types: RuleTypes::All,
        ..Default::default()
    };

    let (mut rules, mut ok_net, mut ok_cos, mut failed) = (0usize, 0usize, 0usize, 0usize);
    let mut converted_bad: Vec<String> = Vec::new();

    for line in std::io::BufReader::new(file).lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => continue,
        };
        let t = line.trim();
        if t.is_empty() || t.starts_with('!') || t.starts_with('[') {
            continue;
        }
        rules += 1;
        let converted = t.contains(":style(") || t.contains(":remove()");
        match parse_filter(t, false, opts) {
            Ok(ParsedLine::Network(_)) => ok_net += 1,
            Ok(ParsedLine::Cosmetic(_)) => ok_cos += 1,
            Err(e) => {
                failed += 1;
                if converted {
                    converted_bad.push(format!("{:?}\t{}", e, t));
                }
            }
        }
    }

    println!(
        "rules={} ok_network={} ok_cosmetic={} failed={} converted_rejected={}",
        rules,
        ok_net,
        ok_cos,
        failed,
        converted_bad.len()
    );

    let mut bad = false;
    if !converted_bad.is_empty() {
        bad = true;
        eprintln!("{} converted rule(s) rejected by adblock-rust:", converted_bad.len());
        for line in converted_bad.iter().take(20) {
            eprintln!("  {}", line);
        }
    }
    if failed > max_failed {
        bad = true;
        eprintln!(
            "rejected rule count {} exceeds the allowed budget of {}",
            failed, max_failed
        );
    }
    if bad {
        std::process::exit(1);
    }
}
