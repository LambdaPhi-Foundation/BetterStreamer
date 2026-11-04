//! BetterStreamer binary: thin CLI over the `better_streamer` library.
//!
//! Phase 0: `run` validates config, builds a synthetic video + trace, and emits
//! a stub `SimulationReport` JSON so the end-to-end plumbing is proven before
//! any ABR algorithm exists.

use std::path::PathBuf;

use better_streamer::simulation::Simulator;
use better_streamer::{
    SimulatorConfig, media::Video, network::NetworkTrace, simulation::SimPolicy,
};
use clap::{Parser, Subcommand, ValueEnum};

/// Content-aware ABR simulator.
#[derive(Debug, Parser)]
#[command(
    name = "betterstreamer",
    version,
    about = "Content-aware ABR simulator (Rust)"
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Debug, Subcommand)]
enum Commands {
    /// Run one policy × video × trace combination (stub report in Phase 0).
    Run(RunArgs),
}

#[derive(Debug, Clone, Copy, ValueEnum)]
enum PolicyArg {
    Baseline,
    Perceptual,
}

#[derive(Debug, Parser)]
struct RunArgs {
    /// ABR policy to simulate.
    #[arg(long, value_enum, default_value_t = PolicyArg::Baseline)]
    policy: PolicyArg,

    /// Video catalog name (synthetic in Phase 0).
    #[arg(long, default_value = "mixed")]
    video: String,

    /// Number of synthetic segments.
    #[arg(long, default_value_t = 8)]
    segments: usize,

    /// Optional trace CSV (`time_s,bandwidth_mbps`). Defaults to synthetic stable-high.
    #[arg(long)]
    trace: Option<PathBuf>,

    /// Where to write the `SimulationReport` JSON (`-` = stdout).
    #[arg(long, default_value = "-")]
    out: String,
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Commands::Run(args) => cmd_run(args),
    }
}

fn cmd_run(args: RunArgs) -> anyhow::Result<()> {
    let config = SimulatorConfig::default();
    config
        .validate()
        .map_err(|e| anyhow::anyhow!(e.to_string()))?;

    let video = Video::synthetic(
        &args.video,
        args.segments,
        config.segment_duration_s,
        &config.ladder_bps,
    )
    .map_err(|e| anyhow::anyhow!(e.to_string()))?;
    println!(
        "video '{}': {} segments x {} representations",
        video.name,
        video.len(),
        config.ladder_bps.len()
    );

    let trace = match &args.trace {
        Some(p) => {
            NetworkTrace::from_csv_file("custom", p).map_err(|e| anyhow::anyhow!(e.to_string()))?
        }
        None => NetworkTrace::constant(
            "stable-high",
            8.0,
            args.segments as f64 * config.segment_duration_s,
            4.0,
        )
        .map_err(|e| anyhow::anyhow!(e.to_string()))?,
    };
    println!("trace '{}': {} samples", trace.name, trace.samples.len());

    let policy = match args.policy {
        PolicyArg::Baseline => SimPolicy::Baseline,
        PolicyArg::Perceptual => SimPolicy::Perceptual,
    };
    let report = Simulator::run(policy, &video, &trace, &config);
    let json = serde_json::to_string_pretty(&report)?;
    if args.out == "-" {
        println!("{json}");
    } else {
        std::fs::write(&args.out, &json)?;
        println!("wrote {}", args.out);
    }
    Ok(())
}
