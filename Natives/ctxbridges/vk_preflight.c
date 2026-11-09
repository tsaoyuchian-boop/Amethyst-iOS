#include "vk_preflight.h"

#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// VkExtensionProperties: char[256] + uint32_t
#define EXT_PROPS_SIZE 260

typedef int32_t (*enum_version_fn)(uint32_t *);
typedef int32_t (*enum_ext_fn)(const char *, uint32_t *, void *);

static void fail(ame_vk_preflight_t *r, const char *msg, const char *detail) {
    r->ok = false;
    snprintf(r->error, sizeof(r->error), "%s%s%s", msg, detail ? ": " : "", detail ? detail : "");
}

static bool has_extension(const char *props, uint32_t count, const char *name) {
    for (uint32_t i = 0; i < count; i++) {
        if (!strncmp(props + (size_t)i * EXT_PROPS_SIZE, name, 255)) return true;
    }
    return false;
}

ame_vk_preflight_t ame_vk_preflight(const char *dylibPath) {
    ame_vk_preflight_t r = { .ok = true };

    void *lib = dlopen(dylibPath, RTLD_LAZY | RTLD_LOCAL);
    if (!lib) {
        fail(&r, "could not load the Vulkan library", dlerror());
        return r;
    }

    enum_version_fn enumVersion = (enum_version_fn)dlsym(lib, "vkEnumerateInstanceVersion");
    enum_ext_fn enumExt = (enum_ext_fn)dlsym(lib, "vkEnumerateInstanceExtensionProperties");
    if (!enumVersion || !enumExt) {
        fail(&r, "the library is not MoltenVK, entry points are missing", NULL);
        return r;
    }
    // LWJGL calls this at startup and refuses to load the library without it.
    if (!dlsym(lib, "vkEnumerateInstanceLayerProperties")) {
        fail(&r, "vkEnumerateInstanceLayerProperties is missing, the driver needs a loader shim", NULL);
        return r;
    }

    // vkEnumerateInstanceVersion was added in Vulkan 1.1. Some iOS Vulkan
    // loader/driver shims export the entry point but cannot answer this query
    // during preflight, even though instance creation and extension discovery
    // work normally. Treat a failed version query as Vulkan 1.0 and let the
    // required surface-extension checks below decide whether the driver is
    // usable. Do not reject an otherwise functional driver based on this
    // optional query alone.
    if (enumVersion(&r.apiVersion) != 0) {
        r.apiVersion = (1u << 22); // VK_API_VERSION_1_0
    }

    uint32_t count = 0;
    if (enumExt(NULL, &count, NULL) != 0 || count == 0) {
        fail(&r, "no instance extensions reported", NULL);
        return r;
    }
    char *props = calloc(count, EXT_PROPS_SIZE);
    if (!props) {
        fail(&r, "out of memory", NULL);
        return r;
    }
    int32_t rc = enumExt(NULL, &count, props);
    // VK_INCOMPLETE (5) still fills what fits
    if (rc != 0 && rc != 5) {
        free(props);
        fail(&r, "vkEnumerateInstanceExtensionProperties failed", NULL);
        return r;
    }

    if (!has_extension(props, count, "VK_KHR_surface")) fail(&r, "VK_KHR_surface is not available", NULL);
    else if (!has_extension(props, count, "VK_EXT_metal_surface")) fail(&r, "VK_EXT_metal_surface is not available", NULL);
    free(props);
    return r;
}
