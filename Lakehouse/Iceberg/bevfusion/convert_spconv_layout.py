"""Permute spconv layer weights from spconv1 layout to spconv2 layout.

The pretrained BEVFusion checkpoint published by OpenMMLab was saved with
spconv1's `[out, kx, ky, kz, in]` weight layout. mmdet3d 1.4.0 ships with
spconv2 which expects `[kx, ky, kz, in, out]`. Loading without permutation
silently leaves the sparse-encoder layers at random init — fatal for any
inference signal.

Usage:
    python convert_spconv_layout.py <input.pth> <output.pth>
"""
import sys
from pathlib import Path
import torch


def main():
    if len(sys.argv) != 3:
        print("Usage: convert_spconv_layout.py <input.pth> <output.pth>")
        sys.exit(1)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])

    state = torch.load(src, map_location="cpu")
    # mmdet3d checkpoints store the weights under "state_dict"
    sd = state.get("state_dict", state)

    n_permuted = 0
    for k, v in list(sd.items()):
        # Target sparse-encoder Conv3d weights inside pts_middle_encoder
        if (
            "pts_middle_encoder" in k
            and k.endswith(".weight")
            and isinstance(v, torch.Tensor)
            and v.dim() == 5
        ):
            # spconv1 [O, kx, ky, kz, I] → spconv2 [kx, ky, kz, I, O]
            sd[k] = v.permute(1, 2, 3, 4, 0).contiguous()
            n_permuted += 1

    if "state_dict" in state:
        state["state_dict"] = sd
    else:
        state = sd

    dst.parent.mkdir(parents=True, exist_ok=True)
    torch.save(state, dst)
    print(f"Permuted {n_permuted} sparse-encoder weights")
    print(f"Wrote {dst} ({dst.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
