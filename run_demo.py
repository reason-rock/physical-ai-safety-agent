import argparse
import os
import sys

from gaitlab.orchestrator import GaitLabOrchestrator


DEFAULT_REQUEST = (
    "The latest matched evaluation packet still shows forward pitch spikes. "
    "Keep the previous stable baseline unchanged on the control training rig, "
    "run one treatment with higher orientation penalty and action smoothing on "
    "the treatment training rig, evaluate both with the same metrics, and decide "
    "whether supported hardware review is justified."
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the public Physical AI Safety Agent demo workflow.")
    parser.add_argument(
        "--data-mode",
        choices=["mock", "real_replay", "live_lab"],
        default="mock",
        help=(
            "Evidence source. 'mock' is fully synthetic. 'real_replay' reads "
            "sanitized lab evidence. 'live_lab' connects to the real GPU0/GPU1 "
            "GPU servers and may, when every safety precondition is met, deploy "
            "to the real robot."
        ),
    )
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help=(
            "Required to actually use --data-mode live_lab. Confirms you are the "
            "on-site operator and that emergency stop is ready."
        ),
    )
    parser.add_argument(
        "--operator-token",
        default=None,
        help=(
            "Optional identifier recorded in the audit log when a live robot "
            "deploy runs. Use your name or initials."
        ),
    )
    parser.add_argument(
        "--request",
        default=DEFAULT_REQUEST,
        help="Experiment request text (defaults to the forward-fall scenario).",
    )
    parser.add_argument(
        "--use-google-api",
        action="store_true",
        help=(
            "Opt in to the optional Google design model. By default the CLI demo "
            "uses deterministic rules so it can run without API keys or quota."
        ),
    )
    args = parser.parse_args()
    if not args.use_google_api:
        os.environ["GAITLAB_USE_GOOGLE_API"] = "false"

    if args.data_mode == "live_lab" and not args.confirm_live:
        print(
            "ERROR: --data-mode live_lab requires --confirm-live.\n"
            "Live lab mode may submit real training jobs to GPU0/GPU1 and, if the "
            "safety gate and operator approval all pass, may deploy a policy to the "
            "real DARwIn-OP robot. Re-run with --confirm-live only if you are the "
            "on-site operator and emergency stop is ready.",
            file=sys.stderr,
        )
        sys.exit(2)

    orchestrator = GaitLabOrchestrator(
        data_mode=args.data_mode,
        operator_token=args.operator_token,
    )
    result = orchestrator.handle_request(args.request)
    print(result.report_markdown)


if __name__ == "__main__":
    main()
