# 模式覆盖率报告（M6-0 自动生成）

- 图库: 208 个标准化图
- 链模式: 1165 条 (df≥阈值)
- 技术 signature: 15 个
- 边界模式: 65 条

## 一、任务能力覆盖（M4' 采集依据）

| 任务面 | 依赖技术 | 库内例数 | 状态 |
|---|---|---|---|
| 身份注入 | PuLID×16, InstantID×20, ReActor/inswapper×2, FaceAnalysis×45 | 45 | 可用 |
| 姿态控制 | OpenPose×6 | 6 | 薄弱 |
| 批量生成 | 批量节点×37 | 37 | 可用 |
| 高清放大 | Upscale-Hires×37 | 37 | 可用 |
| 局部重绘 | Inpaint×37, Kontext×24 | 37 | 可用 |
| 修复/上色 | Florence2×17, BiRefNet×11 | 17 | 可用 |
| 人脸筛选/精修 | FaceDetailer×6, FaceAnalysis×45 | 45 | 薄弱 |
| 视频扩展 | WanVideo×17, VACE×11 | 17 | 可用 |
| 拼接/打包 | 拼接节点×114 | 114 | 可用 |

## 二、缺口清单（M4' 定向采集目标）

- [薄弱] 姿态控制（OpenPose×6）
- [薄弱] 人脸筛选/精修（FaceDetailer×6, FaceAnalysis×45）

### 采集建议

- 主技术（每个 facet 前两个依赖）≥8 例即判可用；缺口以缺口清单为准
- 挖掘渠道优先级：webapp 搜索（batch_webapp.py，技术词命中率高）> 标签翻页（batch_targeted.py）> 关键词深挖（batch_deep.py）；站内 creation 搜索无效

## 三、高频链模式 Top 40（Composer 拼接字典）

| df | 链 |
|---|---|
| 103 | `VAELoader -VAE-> VAEDecode` |
| 98 | `VAELoader -VAE-> VAEDecode -IMAGE-> VAEDecode` |
| 90 | `KSampler -LATENT-> VAEDecode` |
| 84 | `KSampler -LATENT-> VAEDecode -IMAGE-> VAEDecode` |
| 64 | `VAEDecode -IMAGE-> SaveImage` |
| 53 | `RandomNoise -NOISE-> SamplerCustomAdvanced` |
| 52 | `RandomNoise -NOISE-> SamplerCustomAdvanced -LATENT-> SamplerCustomAdvanced` |
| 50 | `UNETLoader -MODEL-> LoraLoaderModelOnly` |
| 49 | `KSamplerSelect -SAMPLER-> SamplerCustomAdvanced` |
| 49 | `KSamplerSelect -SAMPLER-> SamplerCustomAdvanced -LATENT-> SamplerCustomAdvanced` |
| 49 | `UNETLoader -MODEL-> LoraLoaderModelOnly -MODEL-> LoraLoaderModelOnly` |
| 45 | `BasicGuider -GUIDER-> SamplerCustomAdvanced` |
| 45 | `BasicGuider -GUIDER-> SamplerCustomAdvanced -LATENT-> SamplerCustomAdvanced` |
| 44 | `SamplerCustomAdvanced -LATENT-> VAEDecode` |
| 41 | `VAELoader -VAE-> VAEEncode` |
| 40 | `CLIPTextEncode -CONDITIONING-> ConditioningZeroOut` |
| 40 | `DualCLIPLoader -CLIP-> CLIPTextEncode` |
| 40 | `DualCLIPLoader -CLIP-> CLIPTextEncode -CONDITIONING-> CLIPTextEncode` |
| 40 | `VAELoader -VAE-> VAEEncode -LATENT-> VAEEncode` |
| 39 | `LoadImage -IMAGE-> LayerUtility: ImageScaleByAspectRatio V2` |
| 39 | `SamplerCustomAdvanced -LATENT-> VAEDecode -IMAGE-> VAEDecode` |
| 39 | `KSamplerSelect -SAMPLER-> SamplerCustomAdvanced -LATENT-> SamplerCustomAdvanced -IMAGE-> VAEDecode` |
| 38 | `BasicScheduler -SIGMAS-> SamplerCustomAdvanced` |
| 38 | `BasicScheduler -SIGMAS-> SamplerCustomAdvanced -LATENT-> SamplerCustomAdvanced` |
| 38 | `RandomNoise -NOISE-> SamplerCustomAdvanced -LATENT-> SamplerCustomAdvanced -IMAGE-> VAEDecode` |
| 37 | `CLIPTextEncode -CONDITIONING-> ConditioningZeroOut -CONDITIONING-> ConditioningZeroOut` |
| 37 | `LoadImage -IMAGE-> LayerUtility: ImageScaleByAspectRatio V2 -IMAGE-> LayerUtility: ImageScaleByAspectRatio V2` |
| 34 | `ConditioningZeroOut -CONDITIONING-> KSampler` |
| 34 | `ConditioningZeroOut -CONDITIONING-> KSampler -LATENT-> KSampler` |
| 34 | `BasicGuider -GUIDER-> SamplerCustomAdvanced -LATENT-> SamplerCustomAdvanced -IMAGE-> VAEDecode` |
| 32 | `ConditioningZeroOut -CONDITIONING-> KSampler -LATENT-> KSampler -IMAGE-> VAEDecode` |
| 30 | `BasicScheduler -SIGMAS-> SamplerCustomAdvanced -LATENT-> SamplerCustomAdvanced -IMAGE-> VAEDecode` |
| 27 | `InpaintModelConditioning -CONDITIONING-> KSampler` |
| 26 | `CheckpointLoaderSimple -CLIP-> CLIPTextEncode` |
| 26 | `VAEDecode -IMAGE-> PreviewImage` |
| 26 | `InpaintModelConditioning -CONDITIONING-> KSampler -LATENT-> KSampler` |
| 25 | `VAEEncode -LATENT-> KSampler` |
| 25 | `VAEEncode -LATENT-> KSampler -LATENT-> KSampler` |
| 24 | `CheckpointLoaderSimple -VAE-> VAEDecode` |
| 24 | `LoraLoaderModelOnly -MODEL-> LoraLoaderModelOnly` |

## 四、技术 signature

### FaceAnalysis (df=45)
- 节点类型: FaceAnalysisModels, GroundingDinoModelLoader (segment anything), GroundingDinoSAMSegment (segment anything), InstantIDFaceAnalysis, InvertMask (segment anything), LayerMask: LoadSegmentAnythingModels, LayerMask: SegmentAnythingUltra, LayerMask: SegmentAnythingUltra V2, LayerMask: SegmentAnythingUltra V3, SAMLoader

### Upscale-Hires (df=37)
- 节点类型: CR Upscale Image, ImageUpscaleWithModel, LatentUpscaleBy, LatentUpscaleModelLoader, MinimaxH3LatentUpscalerNode3D, SUPIR_Upscale, SeedVR2VideoUpscaler, UltimateSDUpscale, UltimateSDUpscaleCustomSample, UpscaleModelLoader

### Inpaint (df=37)
- 节点类型: BlendInpaint, CutForInpaint, INPAINT_MaskedFill, InpaintCrop, InpaintCropImproved, InpaintModelConditioning, InpaintPreprocessor, InpaintResize, InpaintStitch, InpaintStitchImproved
- 核心边: InpaintModelConditioning OUT CONDITIONING KSampler

### Kontext (df=24)
- 节点类型: Comfly_Flux_Kontext, FluxKontextImageScale, FluxKontextMultiReferenceLatentMethod, RH_ComfyFluxKontext

### InstantID (df=20)
- 节点类型: ApplyInstantID, ApplyInstantIDAdvanced, InstantIDFaceAnalysis, InstantIDModelLoader
- 核心边: CLIPTextEncode CONDITIONING IN ApplyInstantID; CheckpointLoaderSimple MODEL IN ApplyInstantID; ControlNetLoader CONTROL_NET IN ApplyInstantID; InstantIDFaceAnalysis FACEANALYSIS IN ApplyInstantID; InstantIDFaceAnalysis OUT FACEANALYSIS ApplyInstantID; InstantIDModelLoader INSTANTID IN ApplyInstantID; InstantIDModelLoader OUT INSTANTID ApplyInstantID

### ControlNet-apply (df=19)
- 节点类型: ACN_AdvancedControlNetApplySingle_v2, ControlNetApply, ControlNetApplyAdvanced, ControlNetApplySD3

### Florence2 (df=17)
- 节点类型: DownloadAndLoadFlorence2Model, Florence2ModelLoader, Florence2Run, Florence2toCoordinates, LayerMask: LoadFlorence2Model, LayerUtility: Florence2Image2Prompt

### WanVideo (df=17)
- 节点类型: LoadWanVideoClipTextEncoder, LoadWanVideoT5TextEncoder, SkipLayerGuidanceWanVideo, WanVideoAddSCAILPoseEmbeds, WanVideoAddSCAILReferenceEmbeds, WanVideoAnimateEmbeds, WanVideoBlockSwap, WanVideoClipVisionEncode, WanVideoContextOptions, WanVideoDecode
- 核心边: WanVideoBlockSwap BLOCKSWAPARGS IN WanVideoModelLoader; WanVideoBlockSwap OUT BLOCKSWAPARGS WanVideoModelLoader; WanVideoSampler LATENT IN WanVideoDecode; WanVideoSampler OUT LATENT WanVideoDecode; WanVideoTextEncode OUT WANVIDEOTEXTEMBEDS WanVideoSampler; WanVideoTextEncode WANVIDEOTEXTEMBEDS IN WanVideoSampler

### PuLID (df=16)
- 节点类型: ApplyPulid, ApplyPulidFlux, NunchakuPulidApply, NunchakuPulidLoader, PulidEvaClipLoader, PulidFluxEvaClipLoader, PulidFluxFaceDetector, PulidFluxInsightFaceLoader, PulidFluxModelLoader, PulidFluxOptions

### TeaCache (df=14)
- 节点类型: ApplyTeaCachePatch, TeaCache, WanVideoTeaCache, WanVideoTeaCacheKJ

### VACE (df=11)
- 节点类型: WanVaceToVideo, WanVideoVACEEncode, WanVideoVACEModelSelect
- 核心边: WanVideoVACEEncode OUT WANVIDIMAGE_EMBEDS WanVideoSampler; WanVideoVACEModelSelect OUT VACEPATH WanVideoModelLoader

### BiRefNet (df=11)
- 节点类型: AutoDownloadBiRefNetModel, BiRefNetRMBG, LayerMask: BiRefNetUltraV2, LayerMask: LoadBiRefNetModel, LayerMask: LoadBiRefNetModelV2, LoadRembgByBiRefNetModel, RembgByBiRefNet

### FaceDetailer (df=6)
- 节点类型: FaceDetailer
- 核心边: CLIPTextEncode CONDITIONING IN FaceDetailer; FaceDetailer OUT IMAGE SaveImage; UltralyticsDetectorProvider BBOX_DETECTOR IN FaceDetailer

### OpenPose (df=6)
- 节点类型: OpenposePreprocessor

### ReActor/inswapper (df=2)
- 节点类型: ReActorFaceSwap
- 核心边: LoadImage IMAGE IN ReActorFaceSwap; ReActorFaceSwap OUT IMAGE PreviewImage

## 五、边界挂点（Composer 接口面）

**输入侧**

| df | 链 |
|---|---|
| 39 | `LoadImage -IMAGE-> LayerUtility: ImageScaleByAspectRatio V2` |
| 20 | `LoadImage -IMAGE-> Image Comparer (rgthree)` |
| 14 | `LoadImage -IMAGE-> MiniMaxH3ReferenceToVideo` |
| 12 | `LoadImage -IMAGE-> ImageScaleToTotalPixels` |
| 11 | `LoadImage -IMAGE-> ImageResizeKJv2` |
| 10 | `LoadImage -IMAGE-> LayerMask: PersonMaskUltra V2` |
| 9 | `VHS_LoadVideo -AUDIO-> VHS_VideoCombine` |
| 8 | `LoadImage -IMAGE-> ImageResizeKJ` |
| 8 | `LoadImage -IMAGE-> ImageStitch` |
| 8 | `VHS_LoadVideo -IMAGE-> ImageResizeKJ` |
| 7 | `LoadImage -*-> SetNode` |
| 7 | `LoadImage -IMAGE-> ColorMatch` |
| 7 | `LoadImage -IMAGE-> FaceBoundingBox` |
| 7 | `LoadImage -IMAGE-> ImageConcanate` |
| 7 | `LoadImage -MASK-> LayerUtility: ImageScaleByAspectRatio V2` |
| 7 | `VHS_LoadVideo -VHS_VIDEOINFO-> VHS_VideoInfo` |
| 6 | `LoadImage -IMAGE-> ImageConcatMulti` |
| 6 | `LoadImage -IMAGE-> LayerMask: SegmentAnythingUltra V2` |
| 6 | `LoadImage -IMAGE-> LayerUtility: CropByMask V2` |
| 6 | `LoadImage -IMAGE-> RH_Captioner` |
| 5 | `LoadImage -IMAGE-> ImageResize+` |
| 5 | `LoadImage -IMAGE-> LayerUtility: ImageReel` |
| 5 | `LoadImage -IMAGE-> MiniMaxH3AudioConditioningT8` |
| 5 | `LoadImage -IMAGE-> RH_ComfyFluxKontext` |
| 5 | `VHS_LoadVideo -IMAGE-> ImageResizeKJv2` |
| 4 | `LoadImage -IMAGE-> ApplyInstantID` |
| 4 | `LoadImage -IMAGE-> ImageScaleDownToSize` |
| 4 | `LoadImage -IMAGE-> MiniMaxH3ImageToVideo` |
| 4 | `LoadImage -IMAGE-> RH_MinimaxHailuoH3ImageToVideo` |
| 4 | `LoadImage -IMAGE-> easy imageScaleDownToSize` |
| 4 | `VHS_LoadVideo -IMAGE-> LayerUtility: ImageScaleByAspectRatio V2` |

**输出侧**

| df | 链 |
|---|---|
| 64 | `VAEDecode -IMAGE-> SaveImage` |
| 26 | `VAEDecode -IMAGE-> PreviewImage` |
| 13 | `VAEDecode -IMAGE-> VHS_VideoCombine` |
| 11 | `GetNode -IMAGE-> SaveImage` |
| 10 | `ImageConcanate -IMAGE-> SaveImage` |
| 10 | `VAEDecodeAudio -AUDIO-> VHS_VideoCombine` |
| 9 | `LayerUtility: ImageReelComposit -IMAGE-> SaveImage` |
| 9 | `LayerUtility: ImageScaleByAspectRatio V2 -IMAGE-> PreviewImage` |
| 9 | `VHS_LoadVideo -AUDIO-> VHS_VideoCombine` |
| 7 | `ImageConcatMulti -IMAGE-> SaveImage` |
| 7 | `RH_ComfyFluxKontext -IMAGE-> SaveImage` |
| 7 | `TTP_Image_Tile_Batch -IMAGE-> PreviewImage` |
| 6 | `ImageConcanate -IMAGE-> PreviewImage` |
| 6 | `ImageConcatMulti -IMAGE-> VHS_VideoCombine` |
| 5 | `AIO_Preprocessor -IMAGE-> PreviewImage` |
| 5 | `ColorMatch -IMAGE-> SaveImage` |
| 5 | `LayerUtility: CropByMask V2 -IMAGE-> PreviewImage` |
| 5 | `MiniMaxH3AVDecodeT8 -AUDIO-> VHS_VideoCombine` |
| 5 | `MiniMaxH3AVDecodeT8 -IMAGE-> VHS_VideoCombine` |
| 5 | `VHS_VideoInfo -FLOAT-> VHS_VideoCombine` |
| 5 | `easy imageConcat -IMAGE-> PreviewImage` |
| 4 | `ColorMatch -IMAGE-> VHS_VideoCombine` |
| 4 | `FaceBoundingBox -IMAGE-> PreviewImage` |
| 4 | `FaceDetailer -IMAGE-> SaveImage` |
| 4 | `GetNode -IMAGE-> PreviewImage` |
| 4 | `GetVideoComponents -AUDIO-> VHS_VideoCombine` |
| 4 | `GetVideoComponents -FLOAT-> VHS_VideoCombine` |
| 4 | `ImageCompositeMasked -IMAGE-> SaveImage` |
| 4 | `ImageCrop+ -IMAGE-> PreviewImage` |
| 4 | `ImageResizeKJ -IMAGE-> PreviewImage` |
| 4 | `MaskToImage -IMAGE-> PreviewImage` |
| 4 | `SetNode -IMAGE-> PreviewImage` |
| 4 | `WanVideoDecode -IMAGE-> VHS_VideoCombine` |
| 4 | `easy imageConcat -IMAGE-> SaveImage` |

## 六、端口类型兼容表（拼接时类型必须匹配）

| 信号类型 | 主要产出类别 | 主要消费类别 |
|---|---|---|
| diptych_ref_tar | utility | utility |
| WANVIDEOSCHEDULER | preprocessor | utility |
| INT,FLOAT,IMAGE,LATENT | utility | utility |
| NOISE | sampler, utility | sampler, utility |
| MMAUDIO_MODEL | utility | utility |
| SEC_MODEL | utility | preprocessor |
| ANY | utility | utility |
| SAMPLER | sampler, utility | sampler, upscale, utility |
| SUPIRVAE | utility | utility |
| FC_DATA | utility | utility |
| MODEL | utility, checkpoint_loader, lora | utility, sampler, lora |
| EXPERIMENTALARGS | utility | utility |
| LATENT | utility, sampler, vae | vae, sampler, utility |
| VAE | vae, checkpoint_loader, utility | vae, utility, controlnet |
| DICT | utility | utility |
| extra_args | utility | utility |
| NUMBER | utility | utility |
| WANVIDEOMODEL | utility | utility |
| VACEPATH | utility | utility |
| FLORENCE2 | utility | utility |
| FRAMEPACKCOMPILEARGS | utility | utility |
| UPSCALE_MODEL | upscale, utility | upscale |
| MMAUDIO_FEATUREUTILS | utility | utility |
| ANALYSIS_MODELS | face | utility |
| SEEDVR2_VAE | utility | upscale |
| SLGARGS | utility | utility |
| TUPLE | batch | utility |
| FACEANALYSIS | face | face |
| REMBG_SESSION | utility | utility |
| SUPIRMODEL | utility | utility |
| IMAGE_BOUNDS | utility | utility |
| H2 | utility | utility |
| INSTANTID | face | face |
| WANVIDEOTEXTEMBEDS | utility, preprocessor | utility |
| BiRefNetMODEL | utility | utility |
| NLFMODEL | utility | utility |
| BEN_MODEL | utility | utility |
| STYLE_MODEL | conditioning | conditioning, utility |
| IMAGE,MASK | vae | utility |
| SUPIR_cond_neg | utility | utility |
| VIDEO | utility, video_io | video_io, utility |
| WANVIDEOCONTROLNET | controlnet | utility |
| VHS_FILENAMES | video_io | utility |
| SEEDVR2_DIT | utility | upscale, utility |
| NLFPRED | utility | utility |
| AUDIO | utility, vae, video_io | utility, video_io, vae |
| STITCH | utility | utility |
| WARP | utility | utility |
| CONTROL_NET | controlnet, utility | controlnet, face, utility |
| BIREFNET | utility | utility |
| TORCH_COMPILE_ARGS | utility | utility |
| JoyTwoPipeline | utility | utility |
| YOLO_MODEL | utility | utility |
| FLOAT | utility, video_io | utility, video_io, sampler |
| LCS_DATA | utility | postprocess, utility |
| CONDITIONING | utility, conditioning, face | sampler, utility, face |
| LIST | batch, utility | utility |
| SUPIR_cond_pos | utility | utility |
| UNI3C_EMBEDS | utility | utility |
| MELROFORMERMODEL | utility | utility |
| BBOX_DETECTOR | utility | face |
| SHARPNESS_DATA | utility | utility |
| EVA_CLIP | face | face |
| GUIDER | sampler, utility | sampler, utility |
| LAYER | utility | utility |
| block_swap_config | utility | utility |
| CLIP_VISION | clip, conditioning | clip, utility, ipadapter |
| OCPipeline | lora | utility |
| BOX | utility | utility |
| COMPOSITOR_CONFIG | utility | utility |
| EASY_SAM3_MODEL | utility | preprocessor |
| FETAARGS | utility | utility |
| JOYCAPTIONBETA1_MODEL | utility | utility |
| WANCOMPILEARGS | utility | utility |
| GIMMVIF_MODEL | utility | utility |
| BACKGROUND_REMOVAL | utility | utility |
| BOOLEAN | utility | utility, video_io |
| mask_diptych | utility | utility |
| FramePackMODEL | utility | utility |
| COMBO | utility | utility |
| H1 | utility | utility |
| WANVIDSAMPLEREXTRAARGS | utility | utility |
| WANVIDCONTEXT | utility | utility |
| PULIDFLUX | face | face |
| DAMODEL | utility | utility |
| BLOCKSWAPARGS | utility | utility |
| LS_SAM2_MODEL | utility | utility |
| FL2MODEL | utility | utility |
| LLAMACPPARAMS | utility | utility |
| LATENT_UPSCALE_MODEL | upscale | utility |
| FLOAT_PIPE | utility | utility |
| IMAGE | utility, image_io, vae | utility, image_io, conditioning |
| BBOXES | utility | utility |
| MASK | utility, postprocess, preprocessor | utility, postprocess, preprocessor |
| WANVIDIMAGE_CLIPEMBEDS | clip | utility |
| STRING | utility, conditioning, postprocess | utility, conditioning, preprocessor |
| DETAILER_HOOK | utility | face |
| CACHEARGS | utility | utility |
| GROUNDING_DINO_MODEL | utility, preprocessor | utility, preprocessor |
| SEGM_DETECTOR | utility | face |
| SIGMAS | preprocessor, utility, sampler | sampler, utility, upscale |
| PARAMS | utility | utility |
| pipe_prior_output | utility | utility |
| JSON | utility | utility |
| old_tar_image | utility | utility |
| INT | utility, video_io | utility, batch, postprocess |
| * | utility, vae, image_io | utility, batch, postprocess |
| MINIMAX_H3_GENERATION_TAIL | utility | utility |
| COLOR | postprocess | postprocess |
| WANTEXTENCODER | utility | utility |
| Reel | utility | utility |
| FLOW_CONTROL | utility | utility |
| tar_box_yyxx_crop | utility | utility |
| SEGS | utility | utility |
| FLUX_REDUX_MODEL | utility | utility |
| FLUX_FILL_MODEL | utility | utility |
| FLOAT,INT | utility, video_io | video_io |
| SAM2MODEL | utility | preprocessor |
| DREAMO_PROCESSOR | utility | utility |
| CLIP_VISION_OUTPUT | clip | conditioning, utility |
| BIREFNET_MODEL | utility | utility |
| CLIP | clip, checkpoint_loader, utility | conditioning, utility, lora |
| POSE_KEYPOINT | preprocessor | utility |
| POSEMODEL | utility | utility, pose |
| POSEDATA | utility | utility |
| FACE | utility | utility |
| SAM_MODEL | utility, preprocessor | face, preprocessor |
| LLAMACPPMODEL | utility | utility |
| SDPOSE_MODEL | utility | utility |
| TEACACHEARGS | utility | utility |
| W1 | utility | utility |
| RMBGMODEL | utility | utility |
| BBOX | utility | preprocessor |
| PULID | face | face |
| IPADAPTER | face, ipadapter | face, ipadapter |
| INT,FLOAT | utility | utility |
| STITCHER | utility | utility |
| VECTOR | utility | utility |
| WANVIDIMAGE_EMBEDS | utility | utility |
| DWPOSES | pose | utility |
| VHS_VIDEOINFO | video_io | video_io |
| FLOAT,INT,BOOLEAN | utility | utility |
| FPLORA | utility | utility |
| JoyCaption2ExtraOption | utility | utility |
| OPTIONS | face | face |
| LS_SAM_MODELS | preprocessor | preprocessor |
| WANVAE | utility, vae | utility |
| W2 | utility | utility |
| INVSR_PIPE | utility | utility |
| MODEL_PATCH | utility | utility |
| WANVIDLORA | utility | utility |
