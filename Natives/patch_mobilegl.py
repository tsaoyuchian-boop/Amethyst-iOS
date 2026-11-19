#!/usr/bin/env python3
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

APPLIED = "applied"
SKIPPED = "skipped"
FAILED = "failed"
WARNED = "warned"


def read(path):
    return path.read_text(encoding="utf-8")


def write(path, text):
    path.write_text(text, encoding="utf-8")


def replace_once(path, old, new, marker, label, required=True):
    if not path.is_file():
        print(f"[{label}] {path} not found", file=sys.stderr)
        return FAILED if required else WARNED
    text = read(path)
    if marker in text:
        print(f"[{label}] already applied")
        return SKIPPED
    if text.count(old) != 1:
        print(f"[{label}] expected block found {text.count(old)} times in {path.name}, not touching it", file=sys.stderr)
        return FAILED if required else WARNED
    write(path, text.replace(old, new, 1))
    print(f"[{label}] applied")
    return APPLIED


def ios_visibility(root):
    old = """if (APPLE AND MOBILEGL_IOS)
    target_compile_definitions(${CMAKE_PROJECT_NAME} PUBLIC MOBILEGL_IOS=1 _LIBCPP_DISABLE_AVAILABILITY)"""
    new = """if (APPLE AND MOBILEGL_IOS)
    target_compile_definitions(${CMAKE_PROJECT_NAME} PUBLIC MOBILEGL_IOS=1 _LIBCPP_DISABLE_AVAILABILITY)

    set(MOBILEGL_IOS_EXPORTED_SYMBOLS
        "${CMAKE_CURRENT_SOURCE_DIR}/MobileGL/MG_Impl/DyldInterpose/ExportedSymbols.txt")
    target_link_options(${CMAKE_PROJECT_NAME} PRIVATE
        "LINKER:-exported_symbols_list,${MOBILEGL_IOS_EXPORTED_SYMBOLS}")
    set_property(TARGET ${CMAKE_PROJECT_NAME} APPEND PROPERTY
        LINK_DEPENDS "${MOBILEGL_IOS_EXPORTED_SYMBOLS}")"""
    return replace_once(root / "CMakeLists.txt", old, new, "MOBILEGL_IOS_EXPORTED_SYMBOLS", "ios_visibility")


def ios_resolution(root):
    old = """        VkImageBlit blitRegion{};
        blitRegion.srcSubresource.aspectMask = srcBinding.aspectMask;"""
    new = """        // resolution slider: the source fbo is smaller but the dst rect can end up the same size,
        // so stretch it over the whole swapchain and let the blit scale it
        if (drawIsDefaultFbo) {
            const Int requestedSrcWidth = std::abs(srcX1 - srcX0);
            const Int requestedSrcHeight = std::abs(srcY1 - srcY0);
            const Int requestedDstWidth = std::abs(dstX1 - dstX0);
            const Int requestedDstHeight = std::abs(dstY1 - dstY0);

            const Uint32 framebufferWidth = dstBinding.extent.x();
            const Uint32 framebufferHeight = dstBinding.extent.y();

            const Bool isFullscreenScaledBlit =
                requestedSrcWidth > 0 &&
                requestedSrcHeight > 0 &&
                requestedDstWidth == requestedSrcWidth &&
                requestedDstHeight == requestedSrcHeight &&
                (requestedDstWidth != static_cast<Int>(framebufferWidth) ||
                 requestedDstHeight != static_cast<Int>(framebufferHeight));

            if (isFullscreenScaledBlit) {
                dstX0 = 0;
                dstY0 = 0;
                dstX1 = static_cast<GLint>(framebufferWidth);
                dstY1 = static_cast<GLint>(framebufferHeight);
            }
        }

        VkImageBlit blitRegion{};
        blitRegion.srcSubresource.aspectMask = srcBinding.aspectMask;"""
    target = root / "MobileGL/MG_Backend/DirectVulkan/Renderer/VulkanRenderer.cpp"
    return replace_once(target, old, new, "isFullscreenScaledBlit", "ios_resolution")


def hash_shim(root):
    shim_rel = "MobileGL/MG_Util/Compat/libcxx_hash_shim.cpp"
    anchor = "MobileGL/MG_Util/Debug/Log.cpp"

    src = HERE / "libcxx_hash_shim.cpp"
    dst = root / shim_rel
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        print("[hash_shim] copied libcxx_hash_shim.cpp")
    elif not dst.is_file():
        print(f"[hash_shim] {src} missing and {shim_rel} not in the checkout", file=sys.stderr)
        return FAILED

    target = root / "CMakeLists.txt"
    if not target.is_file():
        print(f"[hash_shim] {target} not found", file=sys.stderr)
        return FAILED
    text = read(target)
    if shim_rel in text:
        print("[hash_shim] cmake entry already there")
        return SKIPPED
    if anchor not in text:
        print(f"[hash_shim] anchor {anchor} not in CMakeLists.txt, upstream moved it", file=sys.stderr)
        return FAILED

    out = []
    done = False
    for line in text.splitlines(keepends=True):
        out.append(line)
        if not done and anchor in line:
            out.append(f"\n    {shim_rel}\n")
            done = True
    write(target, "".join(out))
    print("[hash_shim] applied")
    return APPLIED


def to_chars_shim(root):
    # Same mechanism as hash_shim: iOS 15's libc++ lacks the floating-point
    # std::to_chars overloads (annotated iOS 16.3+), which std::format
    # instantiates even for integer/string call sites. Without this shim
    # libMobileGL.dylib compiles but fails to dlopen on iOS 15 with
    # "Symbol not found: __ZNSt3__18to_charsEPcS0_d".
    shim_rel = "MobileGL/MG_Util/Compat/libcxx_to_chars_shim.cpp"
    anchor = "MobileGL/MG_Util/Debug/Log.cpp"

    src = HERE / "libcxx_to_chars_shim.cpp"
    dst = root / shim_rel
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        print("[to_chars_shim] copied libcxx_to_chars_shim.cpp")
    elif not dst.is_file():
        print(f"[to_chars_shim] {src} missing and {shim_rel} not in the checkout", file=sys.stderr)
        return FAILED

    target = root / "CMakeLists.txt"
    if not target.is_file():
        print(f"[to_chars_shim] {target} not found", file=sys.stderr)
        return FAILED
    text = read(target)
    if shim_rel in text:
        print("[to_chars_shim] cmake entry already there")
        return SKIPPED
    if anchor not in text:
        print(f"[to_chars_shim] anchor {anchor} not in CMakeLists.txt, upstream moved it", file=sys.stderr)
        return FAILED

    out = []
    done = False
    for line in text.splitlines(keepends=True):
        out.append(line)
        if not done and anchor in line:
            out.append(f"\n    {shim_rel}\n")
            done = True
    write(target, "".join(out))
    print("[to_chars_shim] applied")
    return APPLIED


def expected_shim(root):
    # Same mechanism as hash_shim / to_chars_shim: iOS 15's libc++ lacks
    # the LLVM 19 key-function symbols for std::bad_expected_access
    # (what() + typeinfo), std::bad_optional_access (what() + D1/D0 +
    # typeinfo + vtable) and std::bad_function_call::what(). Without
    # this shim libMobileGL.dylib compiles but fails to dlopen on iOS 15
    # with "Symbol not found: __ZTINSt3__119bad_expected_accessIvEE".
    # The symbols were confirmed missing from the run #24 dylib with nm:
    # bad_expected_access<void> has only what() + typeinfo undefined,
    # bad_optional_access has all five undefined with no local weak
    # definition, bad_function_call only what(). The shim builds the
    # typeinfo/vtable objects by hand (Itanium ABI) instead of
    # including <expected> / <optional>, so the key-function trap
    # cannot reappear.
    shim_rel = "MobileGL/MG_Util/Compat/libcxx_expected_shim.cpp"
    anchor = "MobileGL/MG_Util/Debug/Log.cpp"

    src = HERE / "libcxx_expected_shim.cpp"
    dst = root / shim_rel
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        print("[expected_shim] copied libcxx_expected_shim.cpp")
    elif not dst.is_file():
        print(f"[expected_shim] {src} missing and {shim_rel} not in the checkout", file=sys.stderr)
        return FAILED

    target = root / "CMakeLists.txt"
    if not target.is_file():
        print(f"[expected_shim] {target} not found", file=sys.stderr)
        return FAILED
    text = read(target)
    if shim_rel in text:
        print("[expected_shim] cmake entry already there")
        return SKIPPED
    if anchor not in text:
        print(f"[expected_shim] anchor {anchor} not in CMakeLists.txt, upstream moved it", file=sys.stderr)
        return FAILED

    out = []
    done = False
    for line in text.splitlines(keepends=True):
        out.append(line)
        if not done and anchor in line:
            out.append(f"\n    {shim_rel}\n")
            done = True
    write(target, "".join(out))
    print("[expected_shim] applied")
    return APPLIED


def layered_attachment_workaround(root):
    # Option A + B for A10 / MoltenVK (run #28, latestlog 2026-11-19):
    # A10 has no Metal layered rendering (Apple5/A12 required), and MobileGL added
    # COLOR_ATTACHMENT usage to EVERY colour texture, so MoltenVK refused to create
    # the layered (cube) view of the main-menu panorama cubemap (textureId=19,
    # GL_TEXTURE_CUBE_MAP, 6 panorama PNGs) at VkTextureManager.cpp:2857 with
    # VK_ERROR_FEATURE_NOT_PRESENT (-8). The render thread then retried the view
    # every frame, spamming FATAL, until the app crashed after "Preparing spawn
    # area: 16%".
    #
    # A: defer attachment usage exactly like STORAGE usage is deferred above -
    # only textures actually attached to a framebuffer get COLOR_ATTACHMENT /
    # DEPTH_STENCIL_ATTACHMENT. Sampled-only textures (the panorama cubemap)
    # never carry the bit, so MoltenVK no longer refuses their layered views.
    # MarkAttachmentTexture is called from GetOrCreateAttachmentViewAtMipLevel,
    # the choke point every attachment-view request passes through, before its
    # sync - so the image is created with attachment usage on first use, and a
    # texture attached later is upgraded through the existing preserve-copy
    # recreate (which restores the old layout, so the render pass manager's
    # tracked layout stays truthful).
    #
    # B: CreateImageView failure is a soft, recoverable driver refusal, not a
    # broken invariant, so it must not go through VK_VERIFY (which logs FATAL on
    # every retry) - check the VkResult directly and report it once, the rule
    # VkIncludes.h states for SyncTextureResource's vmaCreateImage failure.
    # SyncTextureViews additionally latches a view-creation failure per image so
    # a capability refusal is not retried every frame; the latch clears when
    # SyncTextureResource creates a new image, the only thing that can change
    # the outcome.
    h_target = root / "MobileGL/MG_Backend/DirectVulkan/Renderer/VkTextureManager.h"
    cpp_target = root / "MobileGL/MG_Backend/DirectVulkan/Renderer/VkTextureManager.cpp"
    results = []

    results.append(replace_once(h_target,
        """        Bool storageUsageResolved = false;
""",
        """        Bool storageUsageResolved = false;
        // True once this image was (re)resolved while the texture was already marked as a
        // framebuffer attachment (see MarkAttachmentTexture). Mirrors storageUsageResolved:
        // distinguishes "not upgraded yet" from "cannot be upgraded", so the compatibility
        // check that recreates the image on an attachment-usage upgrade can actually fire.
        Bool attachmentUsageResolved = false;
        // Latched when SyncTextureViews fails to create a view for this image: the failure
        // is a driver capability refusal, not a transient error, so retrying it every frame
        // only re-logs the same error. Cleared when SyncTextureResource creates a new image
        // for the texture, which is the only thing that can change the outcome.
        Bool viewCreationFailed = false;
""",
        "attachmentUsageResolved", "layered_attachment"))

    results.append(replace_once(h_target,
        """            std::swap(this->storageUsageResolved, that.storageUsageResolved);
""",
        """            std::swap(this->storageUsageResolved, that.storageUsageResolved);
            std::swap(this->attachmentUsageResolved, that.attachmentUsageResolved);
            std::swap(this->viewCreationFailed, that.viewCreationFailed);
""",
        "viewCreationFailed, that.viewCreationFailed", "layered_attachment"))

    results.append(replace_once(h_target,
        """            storageUsageResolved = false;
            syncedTextureParamsVersion = 0;
""",
        """            storageUsageResolved = false;
            attachmentUsageResolved = false;
            viewCreationFailed = false;
            syncedTextureParamsVersion = 0;
""",
        "viewCreationFailed = false;\n            syncedTextureParamsVersion = 0;", "layered_attachment"))

    results.append(replace_once(h_target,
        """    Bool NeedsStorageUsageUpgrade(MG_State::GLState::ITextureObject& texture) const;
""",
        """    Bool NeedsStorageUsageUpgrade(MG_State::GLState::ITextureObject& texture) const;
    // Records that this texture is attached to a framebuffer, so its image must carry
    // COLOR_ATTACHMENT / DEPTH_STENCIL_ATTACHMENT usage. Called from
    // GetOrCreateAttachmentViewAtMipLevel, the choke point every attachment-view request
    // passes through, before its sync - so the image is created with attachment usage
    // on first use. Sticky for the texture's lifetime, like MarkStorageImageTexture.
    void MarkAttachmentTexture(MG_State::GLState::ITextureObject& texture);
    // True when this texture is marked but its live image predates the mark, i.e. the next
    // sync will recreate it with attachment usage and copy the old contents forward.
    Bool NeedsAttachmentUsageUpgrade(MG_State::GLState::ITextureObject& texture) const;
""",
        "void MarkAttachmentTexture(MG_State::GLState::ITextureObject& texture);", "layered_attachment"))

    results.append(replace_once(h_target,
        """    // Textures that have been bound to a GL image unit (see MarkStorageImageTexture).
    std::unordered_set<TextureIdentity, TextureIdentityHash> m_storageImageTextures;
""",
        """    // Textures that have been bound to a GL image unit (see MarkStorageImageTexture).
    std::unordered_set<TextureIdentity, TextureIdentityHash> m_storageImageTextures;
    // Textures that have been attached to a framebuffer (see MarkAttachmentTexture).
    std::unordered_set<TextureIdentity, TextureIdentityHash> m_attachmentTextures;
""",
        "m_attachmentTextures", "layered_attachment"))

    results.append(replace_once(cpp_target,
        """    Bool VkTextureManager::NeedsStorageUsageUpgrade(MG_State::GLState::ITextureObject& texture) const {
        const TextureIdentity identity = MakeTextureIdentity(&texture);
        if (m_storageImageTextures.find(identity) == m_storageImageTextures.end()) {
            return false;
        }
        const auto it = m_textureResources.find(identity);
        // No image yet: the first sync creates it with STORAGE straight away, so there is nothing
        // to preserve and nothing to order against.
        return it != m_textureResources.end() && it->second.image != VK_NULL_HANDLE &&
               !it->second.storageUsageResolved;
    }
""",
        """    Bool VkTextureManager::NeedsStorageUsageUpgrade(MG_State::GLState::ITextureObject& texture) const {
        const TextureIdentity identity = MakeTextureIdentity(&texture);
        if (m_storageImageTextures.find(identity) == m_storageImageTextures.end()) {
            return false;
        }
        const auto it = m_textureResources.find(identity);
        // No image yet: the first sync creates it with STORAGE straight away, so there is nothing
        // to preserve and nothing to order against.
        return it != m_textureResources.end() && it->second.image != VK_NULL_HANDLE &&
               !it->second.storageUsageResolved;
    }

    void VkTextureManager::MarkAttachmentTexture(MG_State::GLState::ITextureObject& texture) {
        m_attachmentTextures.insert(MakeTextureIdentity(&texture));
    }

    Bool VkTextureManager::NeedsAttachmentUsageUpgrade(MG_State::GLState::ITextureObject& texture) const {
        const TextureIdentity identity = MakeTextureIdentity(&texture);
        if (m_attachmentTextures.find(identity) == m_attachmentTextures.end()) {
            return false;
        }
        const auto it = m_textureResources.find(identity);
        // No image yet: the first sync creates it with attachment usage straight away, so there
        // is nothing to preserve and nothing to order against.
        return it != m_textureResources.end() && it->second.image != VK_NULL_HANDLE &&
               !it->second.attachmentUsageResolved;
    }
""",
        "void VkTextureManager::MarkAttachmentTexture", "layered_attachment"))

    results.append(replace_once(cpp_target,
        """        const Bool storageUpgradePending =
            !outResource.storageUsageResolved &&
            m_storageImageTextures.find(MakeTextureIdentity(&texture)) != m_storageImageTextures.end();
""",
        """        const Bool storageUpgradePending =
            !outResource.storageUsageResolved &&
            m_storageImageTextures.find(MakeTextureIdentity(&texture)) != m_storageImageTextures.end();
        // Same shape for a pending attachment-usage upgrade: nothing about the texture's
        // content or params changed, but the image itself must be recreated with attachment
        // usage before it can back a framebuffer attachment.
        const Bool attachmentUpgradePending = NeedsAttachmentUsageUpgrade(texture);
""",
        "attachmentUpgradePending", "layered_attachment"))

    results.append(replace_once(cpp_target,
        """        if (outResource.image != VK_NULL_HANDLE && !storageUpgradePending && !viewFlagUpgradePending &&
""",
        """        if (outResource.image != VK_NULL_HANDLE && !storageUpgradePending && !attachmentUpgradePending &&
            !viewFlagUpgradePending &&
""",
        "!attachmentUpgradePending", "layered_attachment"))

    results.append(replace_once(cpp_target,
        """        VkImageUsageFlags desiredUsage =
            VK_IMAGE_USAGE_SAMPLED_BIT |
            (supportsStorageImage ? VK_IMAGE_USAGE_STORAGE_BIT : 0) |
            ((aspect & VK_IMAGE_ASPECT_COLOR_BIT) ? VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT : 0) |
            (((aspect & VK_IMAGE_ASPECT_DEPTH_BIT) || (aspect & VK_IMAGE_ASPECT_STENCIL_BIT)) ?
                 VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT :
                 0);
""",
        """        // Attachment usage is deferred exactly like STORAGE usage above: only textures
        // that have actually been attached to a framebuffer get COLOR_ATTACHMENT /
        // DEPTH_STENCIL_ATTACHMENT. Requesting it for every colour texture makes MoltenVK
        // refuse layered (cube/array) views on GPUs without layered rendering (A10) - the
        // main-menu panorama cubemap is sampled-only and must never carry it.
        // MarkAttachmentTexture upgrades a texture before its first attachment-view sync,
        // and the usage below feeds the compatibility check so the upgrade recreates the image.
        const Bool markedAsAttachmentTexture =
            m_attachmentTextures.find(MakeTextureIdentity(
                const_cast<MG_State::GLState::ITextureObject*>(&texture))) != m_attachmentTextures.end();
        VkImageUsageFlags desiredUsage =
            VK_IMAGE_USAGE_SAMPLED_BIT |
            (supportsStorageImage ? VK_IMAGE_USAGE_STORAGE_BIT : 0) |
            ((markedAsAttachmentTexture && (aspect & VK_IMAGE_ASPECT_COLOR_BIT)) ?
                 VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT :
                 0) |
            ((markedAsAttachmentTexture &&
              ((aspect & VK_IMAGE_ASPECT_DEPTH_BIT) || (aspect & VK_IMAGE_ASPECT_STENCIL_BIT))) ?
                 VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT :
                 0);
""",
        "markedAsAttachmentTexture", "layered_attachment"))

    results.append(replace_once(cpp_target,
        """            resource.storageUsageResolved = markedAsStorageImage;
            return true;
""",
        """            resource.storageUsageResolved = markedAsStorageImage;
            resource.attachmentUsageResolved = markedAsAttachmentTexture;
            return true;
""",
        "attachmentUsageResolved = markedAsAttachmentTexture;\n            return true;", "layered_attachment"))

    results.append(replace_once(cpp_target,
        """        resource.storageUsageResolved = markedAsStorageImage;
        resource.syncedTextureParamsVersion = 0;
""",
        """        resource.storageUsageResolved = markedAsStorageImage;
        resource.attachmentUsageResolved = markedAsAttachmentTexture;
        // A new image can change a view-creation outcome, so a previous SyncTextureViews
        // failure must not latch across the recreate.
        resource.viewCreationFailed = false;
        resource.syncedTextureParamsVersion = 0;
""",
        "resource.viewCreationFailed = false;\n        resource.syncedTextureParamsVersion = 0;", "layered_attachment"))

    results.append(replace_once(cpp_target,
        """    VkImageView VkTextureManager::GetOrCreateAttachmentViewAtMipLevel(MG_State::GLState::ITextureObject& texture,
                                                                      Uint32 mipLevel, Uint32 baseArrayLayer,
                                                                      Uint32 layerCount,
                                                                      VkImageViewType viewType) {
        TextureResource* resource = SyncTextureAndGetDescriptor(texture);
""",
        """    VkImageView VkTextureManager::GetOrCreateAttachmentViewAtMipLevel(MG_State::GLState::ITextureObject& texture,
                                                                      Uint32 mipLevel, Uint32 baseArrayLayer,
                                                                      Uint32 layerCount,
                                                                      VkImageViewType viewType) {
        // Every caller of this function is asking for a framebuffer-attachment view, so this
        // is where a texture earns attachment usage (see MarkAttachmentTexture). Marking
        // before the sync below means the image is created with attachment usage on first
        // use; textures that are only ever sampled never get the bit, which is what keeps
        // MoltenVK from refusing their layered views on GPUs without layered rendering (A10).
        MarkAttachmentTexture(texture);
        TextureResource* resource = SyncTextureAndGetDescriptor(texture);
""",
        "MarkAttachmentTexture(texture);\n        TextureResource* resource = SyncTextureAndGetDescriptor(texture);", "layered_attachment"))

    results.append(replace_once(cpp_target,
        """        VkImageView view = VK_NULL_HANDLE;
        VK_VERIFY(vkCreateImageView(m_device, &viewInfo, nullptr, &view), "vkCreateImageView(texture)");
        return view;
""",
        """        VkImageView view = VK_NULL_HANDLE;
        // Soft failure, not a broken invariant: a driver may legitimately refuse a view
        // (MoltenVK refuses layered views on GPUs without layered rendering), and every
        // caller treats VK_NULL_HANDLE as a recoverable decline. VK_VERIFY would log FATAL
        // on every retry, so check the result directly and report it once - the same rule
        // VkIncludes.h states for SyncTextureResource's vmaCreateImage failure.
        const VkResult viewResult = vkCreateImageView(m_device, &viewInfo, nullptr, &view);
        if (viewResult != VK_SUCCESS) {
            MGLOG_E_ONCE("CreateImageView failed (%d) viewType=%d layers=[%u, %u) format=%d",
                         viewResult, static_cast<Int>(viewType), baseArrayLayer,
                         baseArrayLayer + layerCount, static_cast<Int>(format));
            return VK_NULL_HANDLE;
        }
        return view;
""",
        "CreateImageView failed (%d) viewType=%d", "layered_attachment"))

    results.append(replace_once(cpp_target,
        """        const Bool needsRecreate =
            resource.fullView == VK_NULL_HANDLE ||
            resource.sampledView == VK_NULL_HANDLE ||
            resource.sampledBaseMipLevel != baseMipLevel ||
            resource.sampledLevelCount != levelCount ||
            resource.syncedTextureParamsVersion != texture.GetTextureParamsVersion();
        if (!needsRecreate) {
            return true;
        }
""",
        """        const Bool needsRecreate =
            resource.fullView == VK_NULL_HANDLE ||
            resource.sampledView == VK_NULL_HANDLE ||
            resource.sampledBaseMipLevel != baseMipLevel ||
            resource.sampledLevelCount != levelCount ||
            resource.syncedTextureParamsVersion != texture.GetTextureParamsVersion();
        if (!needsRecreate) {
            return true;
        }
        if (resource.viewCreationFailed) {
            // A view for this image already failed to be created and the image has not been
            // recreated since (SyncTextureResource clears the latch when it creates a new
            // image). The failure is a driver capability refusal, so recreating the same
            // views would only re-log the same error every frame - see the panorama cubemap
            // on A10/MoltenVK. Decline quietly and let the draw fall back to the descriptor
            // fallback texture.
            return false;
        }
""",
        "if (resource.viewCreationFailed) {", "layered_attachment"))

    results.append(replace_once(cpp_target,
        """        resource.fullView = CreateImageView(resource.image, resource.format, resource.aspect, resource.viewType,
                                            baseMipLevel, levelCount, 0, resource.arrayLayers, &sampledComponents);
        if (resource.fullView == VK_NULL_HANDLE) {
            return false;
        }
""",
        """        resource.fullView = CreateImageView(resource.image, resource.format, resource.aspect, resource.viewType,
                                            baseMipLevel, levelCount, 0, resource.arrayLayers, &sampledComponents);
        if (resource.fullView == VK_NULL_HANDLE) {
            resource.viewCreationFailed = true;
            return false;
        }
""",
        "fullView == VK_NULL_HANDLE) {\n            resource.viewCreationFailed = true;", "layered_attachment"))

    results.append(replace_once(cpp_target,
        """        resource.sampledView = CreateImageView(resource.image, resource.format, sampledAspect, resource.viewType,
                                               baseMipLevel, levelCount, 0, resource.arrayLayers, &sampledComponents);
        if (resource.sampledView == VK_NULL_HANDLE) {
            return false;
        }
""",
        """        resource.sampledView = CreateImageView(resource.image, resource.format, sampledAspect, resource.viewType,
                                               baseMipLevel, levelCount, 0, resource.arrayLayers, &sampledComponents);
        if (resource.sampledView == VK_NULL_HANDLE) {
            resource.viewCreationFailed = true;
            return false;
        }
""",
        "sampledView == VK_NULL_HANDLE) {\n            resource.viewCreationFailed = true;", "layered_attachment"))

    if FAILED in results:
        return FAILED
    if APPLIED in results:
        return APPLIED
    return SKIPPED


def enable_availability(root):
    # Keep _LIBCPP_DISABLE_AVAILABILITY for iOS 15 builds.
    # Apple's libc++ std::format currently instantiates floating-point to_chars
    # helpers annotated as iOS 16.3+, even when the call sites format strings
    # or integers. Removing this define makes MobileGL fail to compile against
    # the iOS 15 deployment target. Do not strip the availability suppression.
    print("[enable_availability] keeping _LIBCPP_DISABLE_AVAILABILITY for iOS 15")
    return SKIPPED

def glslang(root):
    target = root / "3rdparty/glslang/SPIRV/GlslangToSpv.cpp"
    old = """// Convert a glslang AST swizzle node to a swizzle vector for building SPIR-V.
void TGlslangToSpvTraverser::convertSwizzle(const glslang::TIntermAggregate& node, std::vector<unsigned>& swizzle)
{
    const glslang::TIntermSequence& swizzleSequence = node.getSequence();
    for (int i = 0; i < (int)swizzleSequence.size(); ++i)
        swizzle.push_back(swizzleSequence[i]->getAsConstantUnion()->getConstArray()[0].getIConst());
}"""
    new = """// Convert a glslang AST swizzle node to a swizzle vector for building SPIR-V.
void TGlslangToSpvTraverser::convertSwizzle(const glslang::TIntermAggregate& node, std::vector<unsigned>& swizzle)
{
    const glslang::TIntermSequence& swizzleSequence = node.getSequence();
    for (int i = 0; i < (int)swizzleSequence.size(); ++i) {
        // non-constant index node used to null deref and kill the whole jvm, fall back to .x instead
        const glslang::TIntermConstantUnion* constUnion = swizzleSequence[i]->getAsConstantUnion();
        if (constUnion == nullptr) {
            fprintf(stderr, "[glslang] convertSwizzle: non-constant swizzle index element %d, using component 0\\n", i);
            swizzle.push_back(0);
            continue;
        }
        swizzle.push_back(constUnion->getConstArray()[0].getIConst());
    }
}"""
    return replace_once(target, old, new, "using component 0", "glslang", required=False)


def log_to_stderr(root):
    old = """            WriteToFile(out.c_str());

            va_end(args);"""
    new = """#if defined(MOBILEGL_IOS)
            // warnings and up also go to stderr so they land in latestlog.txt, MOBILEGL_LOG_CONSOLE=1 sends everything
            static const bool mirrorAll = std::getenv("MOBILEGL_LOG_CONSOLE") != nullptr;
            static int mirrored = 0;
            if (mirrorAll || (mirrored < 2000 && (levelTag[0] == 'W' || levelTag[0] == 'E' || levelTag[0] == 'F'))) {
                mirrored++;
                std::fputs(out.c_str(), stderr);
            }
#endif
            WriteToFile(out.c_str());

            va_end(args);"""
    target = root / "MobileGL/MG_Util/Debug/Log.cpp"
    return replace_once(target, old, new, "MOBILEGL_LOG_CONSOLE", "log_to_stderr", required=False)


STEPS = [
    ("ios_visibility", ios_visibility, True),
    ("ios_resolution", ios_resolution, True),
    ("hash_shim", hash_shim, True),
    ("to_chars_shim", to_chars_shim, True),
    ("expected_shim", expected_shim, True),
    ("layered_attachment_workaround", layered_attachment_workaround, True),
    ("enable_availability", enable_availability, True),
    ("glslang", glslang, False),
    ("log_to_stderr", log_to_stderr, False),
]


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <path-to-mobilegl-checkout>", file=sys.stderr)
        return 1

    root = Path(sys.argv[1]).resolve()
    if not (root / "CMakeLists.txt").is_file():
        print(f"{root} doesn't look like a MobileGL checkout", file=sys.stderr)
        return 1

    failed = []
    for name, step, required in STEPS:
        try:
            result = step(root)
        except Exception as e:
            print(f"[{name}] crashed: {e}", file=sys.stderr)
            result = FAILED if required else WARNED
        if result == FAILED:
            failed.append(name)

    if failed:
        print("patch_mobilegl: failed steps: " + ", ".join(failed), file=sys.stderr)
        return 1
    print("patch_mobilegl: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
