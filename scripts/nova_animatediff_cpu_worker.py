"""Render one AnimateDiff CPU clip for Nova's local media engine."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--motion-adapter-path", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative-prompt", default="")
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--frames", type=int, required=True)
    parser.add_argument("--fps", type=int, required=True)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--device",
        choices=("cpu", "cuda"),
        default="cpu",
        help="Run the AnimateDiff render on CPU or CUDA.",
    )
    parser.add_argument("--local-files-only", action="store_true")
    return parser


def configure_pipeline_device(pipe, device: str) -> str:
    if device == "cuda":
        pipe.enable_model_cpu_offload()
        return "model_cpu_offload"
    pipe.to(device)
    return f"direct_{device}"


def main() -> None:

    args = _parser().parse_args()
    import torch
    from diffusers import AnimateDiffPipeline, DDIMScheduler, MotionAdapter
    from diffusers.utils import export_to_video

    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but PyTorch cannot see a local GPU.")

    model_path = Path(args.model_path).resolve()
    adapter_path = Path(args.motion_adapter_path).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Recent diffusers releases look for the canonical safetensors filename
    # and ignore MotionAdapter's older ``weight_name`` argument. The official
    # adapter is commonly downloaded with an fp16 suffix, so expose it under
    # the canonical name without duplicating the 1.8 GB file when possible.
    canonical_weights = adapter_path / "diffusion_pytorch_model.safetensors"
    fp16_weights = adapter_path / "diffusion_pytorch_model.fp16.safetensors"
    if not canonical_weights.exists() and fp16_weights.exists():
        try:
            os.link(fp16_weights, canonical_weights)
        except OSError:
            shutil.copy2(fp16_weights, canonical_weights)

    # The local SD 1.5 exports are also fp16-suffixed. Normalize the names
    # expected by diffusers 0.40 (hard links keep disk usage unchanged).
    for relative_dir, legacy_name, canonical_name in (
        ("unet", "diffusion_pytorch_model.fp16.safetensors", "diffusion_pytorch_model.safetensors"),
        ("vae", "diffusion_pytorch_model.fp16.safetensors", "diffusion_pytorch_model.safetensors"),
        ("text_encoder", "model.fp16.safetensors", "model.safetensors"),
        ("safety_checker", "model.fp16.safetensors", "model.safetensors"),
    ):
        legacy = model_path / relative_dir / legacy_name
        canonical = model_path / relative_dir / canonical_name
        if not canonical.exists() and legacy.exists():
            try:
                os.link(legacy, canonical)
            except OSError:
                shutil.copy2(legacy, canonical)

    # CPU PyTorch builds do not implement the full fp16 convolution path.
    # Load the downloaded fp16 weights as float32 so the render completes
    # reliably on machines without CUDA (at the cost of speed and RAM).
    dtype = torch.float32 if args.device == "cpu" else torch.float16
    adapter = MotionAdapter.from_pretrained(
        str(adapter_path),
        torch_dtype=dtype,
        local_files_only=args.local_files_only,
    )
    pipe = AnimateDiffPipeline.from_pretrained(
        str(model_path),
        motion_adapter=adapter,
        torch_dtype=dtype,
        local_files_only=args.local_files_only,
    )
    # AnimateDiff's motion module is trained with the SD 1.5 DDIM schedule.
    # DreamShaper ships a DEIS scheduler config; loading that config into a
    # DDIM class produces washed-out/noise-only frames, so use the canonical
    # SD 1.5 beta schedule explicitly.
    pipe.scheduler = DDIMScheduler.from_config(
        pipe.scheduler.config,
        beta_schedule="linear",
        clip_sample=False,
        timestep_spacing="linspace",
        steps_offset=1,
    )
    if hasattr(pipe, "enable_vae_slicing"):
        pipe.enable_vae_slicing()
    # AnimateDiffPipeline does not expose VAE slicing in every diffusers
    # release. Keep the device explicit so it never silently changes modes.
    configure_pipeline_device(pipe, args.device)
    generator_device = "cuda" if args.device == "cuda" else "cpu"
    generator = torch.Generator(device=generator_device).manual_seed(int(args.seed))
    with torch.inference_mode():
        result = pipe(
            prompt=args.prompt,
            negative_prompt=args.negative_prompt or None,
            width=int(args.width),
            height=int(args.height),
            num_frames=int(args.frames),
            num_inference_steps=int(args.steps),
            guidance_scale=7.5,
            generator=generator,
        )
    export_to_video(result.frames[0], str(output_path), fps=int(args.fps))


if __name__ == "__main__":
    main()
