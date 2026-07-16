import os
import tempfile

import torch
from diffusers import AutoencoderKL, StableDiffusionPipeline, UNet2DConditionModel


class gen_texture:
    def __init__(self, model_dir="./nn/material_gen"):
        sd_device = "cuda"
        model_dir = os.path.abspath(model_dir)

        self.vae_diffuse = AutoencoderKL.from_pretrained(
            os.path.join(model_dir, "refine_vae"),
            subfolder="vae_checkpoint_diffuse",
            revision="fp16",
            local_files_only=True,
            torch_dtype=torch.float16,
        ).half().to(sd_device)
        self.vae_normal = AutoencoderKL.from_pretrained(
            os.path.join(model_dir, "refine_vae"),
            subfolder="vae_checkpoint_normal",
            revision="fp16",
            local_files_only=True,
            torch_dtype=torch.float16,
        ).half().to(sd_device)
        self.vae_roughness = AutoencoderKL.from_pretrained(
            os.path.join(model_dir, "refine_vae"),
            subfolder="vae_checkpoint_roughness",
            revision="fp16",
            local_files_only=True,
            torch_dtype=torch.float16,
        ).half().to(sd_device)

        # A prior forge download placed the UNet blob under
        # unet/material_gen/unet while leaving its config at unet/. Accept that
        # recoverable layout without mutating or duplicating the shared weights.
        unet = None
        unet_file = os.path.join(model_dir, "unet", "diffusion_pytorch_model.bin")
        nested_unet = os.path.join(model_dir, "unet", "material_gen")
        if not os.path.isfile(unet_file) and os.path.isfile(
            os.path.join(nested_unet, "unet", "diffusion_pytorch_model.bin")
        ):
            # The nested blob was downloaded without its adjacent config. Build
            # a disposable, correctly-shaped view using symlinks; shared model
            # storage remains untouched and no multi-GB file is copied.
            with tempfile.TemporaryDirectory(prefix="dresscode-unet-") as staging:
                os.symlink(
                    os.path.join(model_dir, "unet", "config.json"),
                    os.path.join(staging, "config.json"),
                )
                os.symlink(
                    os.path.join(nested_unet, "unet", "diffusion_pytorch_model.bin"),
                    os.path.join(staging, "diffusion_pytorch_model.bin"),
                )
                unet = UNet2DConditionModel.from_pretrained(
                    staging,
                    local_files_only=True,
                    torch_dtype=torch.float16,
                )

        self.invpipe = StableDiffusionPipeline.from_pretrained(
            model_dir,
            torch_dtype=torch.float16,
            safety_checker=None,
            vae=self.vae_diffuse,
            unet=unet,
            local_files_only=True,
        ).to(sd_device)

        def patch_conv(module):
            if isinstance(module, torch.nn.Conv2d):
                module.padding_mode = "circular"

        self.invpipe.unet.apply(patch_conv)
        self.invpipe.vae.apply(patch_conv)
        self.vae_diffuse.apply(patch_conv)
        self.vae_normal.apply(patch_conv)
        self.vae_roughness.apply(patch_conv)

    def run(self, prompt, out_folder, seed=None):
        with torch.no_grad():
            generator = None
            if seed is not None:
                generator = torch.Generator(device="cuda").manual_seed(seed)
            latents = self.invpipe(
                [prompt],
                512,
                512,
                generator=generator,
                output_type="latent",
                return_dict=True,
            )[0]

            pt = self.vae_diffuse.decode(
                latents / self.vae_diffuse.config.scaling_factor,
                return_dict=False,
            )[0]
            diffuse = self.invpipe.image_processor.postprocess(
                pt, output_type="pil", do_denormalize=[True]
            )[0]
            diffuse.save(os.path.join(out_folder, "texture_diffuse.png"))

            pt = self.vae_normal.decode(
                latents / self.vae_normal.config.scaling_factor,
                return_dict=False,
            )[0]
            normal = self.invpipe.image_processor.postprocess(
                pt, output_type="pil", do_denormalize=[True]
            )[0]
            normal.save(os.path.join(out_folder, "texture_normal.png"))

            pt = self.vae_roughness.decode(
                latents / self.vae_roughness.config.scaling_factor,
                return_dict=False,
            )[0]
            roughness = self.invpipe.image_processor.postprocess(
                pt, output_type="pil", do_denormalize=[True]
            )[0]
            roughness.save(os.path.join(out_folder, "texture_roughness.png"))


if __name__ == "__main__":
    Gen = gen_texture()
    Gen.run("Deep grey fabric", "./")
