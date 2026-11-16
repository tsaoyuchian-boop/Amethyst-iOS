// Fallback implementations of std::__1::to_chars (floating-point) for
// iOS 15, whose system libc++.1.dylib lacks these symbols (they are
// annotated iOS 16.3+ in Apple's libc++ headers).
//
// Why this is needed: MobileGL uses std::format in many places, e.g.
// MobileGL/MG_Util/ShaderTranspiler/ShaderCompiler.cpp:87
//     String text = std::format("{}", value);   // value is a float
// Apple's libc++ std::format instantiates the floating-point to_chars
// helpers even when the call site only formats strings or integers.
// With _LIBCPP_DISABLE_AVAILABILITY (kept on purpose, see
// Natives/patch_mobilegl.py enable_availability()) the code compiles
// against the iOS 15 deployment target, but libMobileGL.dylib then fails
// to load at runtime with:
//     Symbol not found: __ZNSt3__18to_charsEPcS0_d
//     Expected in: '/usr/lib/libc++.1.dylib'
// (latestlog.txt, 2026-11-17 00:06:36, iPhone 7 Plus / iOS 15.8.8.)
//
// This follows the exact pattern of Natives/libcxx_hash_shim.cpp: define
// our own functions and force the libc++ mangled symbol name with
// __asm__(), so the dynamic linker resolves the reference inside
// libMobileGL.dylib to this file instead of the system libc++.
//
// Precision note: snprintf with %.17g (double) / %.9g (float) gives a
// round-trip representation, not libc++'s shortest round-trip spelling
// (e.g. it may print more digits). MobileGL uses std::format for error /
// debug strings and for GLSL literals such as the tessellation level in
// ShaderCompiler.cpp, where the value still round-trips correctly, so
// this is acceptable. __attribute__((used)) keeps LTO
// (MOBILEGL_ENABLE_LTO=ON) from discarding these symbols, which look
// unreferenced because nothing calls them by their C++ name.
//
// Covered overloads (float / double / long double x plain / chars_format /
// chars_format + precision). On arm64 iOS, long double is 64-bit, the
// same as double, so the long double overloads forward to the double
// implementation. The long double mangled names could not be confirmed
// from the iOS 15 crash log (only the double one was observed); defining
// them is harmless if nothing references them.
#include <charconv>
#include <cstdio>
#include <cstring>
#include <string>
#include <system_error>

namespace {

// Format one floating-point value into [first, last) using snprintf.
// Returns {first + written, errc()} on success, or
// {first, errc::value_too_large} when the buffer is too small.
std::to_chars_result format_float(char *first, char *last, double value,
                                  bool is_float, std::chars_format fmt,
                                  int precision, bool has_precision) {
    char conv = 'g';
    if (fmt == std::chars_format::scientific) {
        conv = 'e';
    } else if (fmt == std::chars_format::fixed) {
        conv = 'f';
    } else if (fmt == std::chars_format::hex) {
        conv = 'a';
    } else {  // general (or anything else): shortest-style %g
        conv = 'g';
    }

    // Build the printf format string.
    char fmtbuf[16];
    if (has_precision && precision >= 0) {
        std::snprintf(fmtbuf, sizeof(fmtbuf), "%%.*%c", conv);
    } else if (conv == 'g') {
        // Shortest round-trip precision: 17 significant digits for
        // double, 9 for float.
        std::snprintf(fmtbuf, sizeof(fmtbuf), is_float ? "%%.9g" : "%%.17g");
    } else if (conv == 'e') {
        std::snprintf(fmtbuf, sizeof(fmtbuf), is_float ? "%%.8e" : "%%.16e");
    } else if (conv == 'f') {
        std::snprintf(fmtbuf, sizeof(fmtbuf), is_float ? "%%.8f" : "%%.16f");
    } else {  // hex
        std::snprintf(fmtbuf, sizeof(fmtbuf), is_float ? "%%.8a" : "%%.16a");
    }

    int needed;
    if (has_precision && precision >= 0) {
        needed = std::snprintf(nullptr, 0, fmtbuf, precision, value);
    } else {
        needed = std::snprintf(nullptr, 0, fmtbuf, value);
    }
    if (needed < 0) {
        return {first, std::errc::invalid_argument};
    }
    if (needed >= (last - first)) {
        return {first, std::errc::value_too_large};
    }

    std::string tmp(static_cast<std::size_t>(needed) + 1, '\0');
    if (has_precision && precision >= 0) {
        std::snprintf(tmp.data(), tmp.size(), fmtbuf, precision, value);
    } else {
        std::snprintf(tmp.data(), tmp.size(), fmtbuf, value);
    }
    tmp.resize(static_cast<std::size_t>(needed));

    if (conv == 'a') {
        // printf %a spells "0x1.8p+1"; to_chars hex spells "1.8p+1".
        if (tmp.compare(0, 2, "0x") == 0) {
            tmp.erase(0, 2);
        } else if (tmp.compare(0, 3, "-0x") == 0) {
            tmp.erase(1, 2);
        }
    }

    const std::size_t len = tmp.size();
    if (static_cast<std::ptrdiff_t>(len) >= (last - first)) {
        return {first, std::errc::value_too_large};
    }
    std::memcpy(first, tmp.data(), len);
    return {first + static_cast<std::ptrdiff_t>(len), std::errc()};
}

std::to_chars_result to_chars_double(char *first, char *last, double value,
                                     std::chars_format fmt, int precision,
                                     bool has_precision) {
    return format_float(first, last, value, false, fmt, precision,
                        has_precision);
}

std::to_chars_result to_chars_float(char *first, char *last, float value,
                                    std::chars_format fmt, int precision,
                                    bool has_precision) {
    return format_float(first, last, static_cast<double>(value), true, fmt,
                        precision, has_precision);
}

}  // namespace

// --- double ---------------------------------------------------------------

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_double(char *first, char *last, double value)
    __asm__("__ZNSt3__18to_charsEPcS0_d");

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_double(char *first, char *last, double value) {
    return to_chars_double(first, last, value, std::chars_format::general,
                           -1, false);
}

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_double_fmt(char *first, char *last, double value,
                               std::chars_format fmt)
    __asm__("__ZNSt3__18to_charsEPcS0_dNS_12chars_formatE");

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_double_fmt(char *first, char *last, double value,
                               std::chars_format fmt) {
    return to_chars_double(first, last, value, fmt, -1, false);
}

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_double_fmt_prec(char *first, char *last, double value,
                                    std::chars_format fmt, int precision)
    __asm__("__ZNSt3__18to_charsEPcS0_dNS_12chars_formatEi");

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_double_fmt_prec(char *first, char *last, double value,
                                    std::chars_format fmt, int precision) {
    return to_chars_double(first, last, value, fmt, precision, true);
}

// --- float ----------------------------------------------------------------

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_float(char *first, char *last, float value)
    __asm__("__ZNSt3__18to_charsEPcS0_f");

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_float(char *first, char *last, float value) {
    return to_chars_float(first, last, value, std::chars_format::general,
                          -1, false);
}

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_float_fmt(char *first, char *last, float value,
                              std::chars_format fmt)
    __asm__("__ZNSt3__18to_charsEPcS0_fNS_12chars_formatE");

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_float_fmt(char *first, char *last, float value,
                              std::chars_format fmt) {
    return to_chars_float(first, last, value, fmt, -1, false);
}

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_float_fmt_prec(char *first, char *last, float value,
                                   std::chars_format fmt, int precision)
    __asm__("__ZNSt3__18to_charsEPcS0_fNS_12chars_formatEi");

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_float_fmt_prec(char *first, char *last, float value,
                                   std::chars_format fmt, int precision) {
    return to_chars_float(first, last, value, fmt, precision, true);
}

// --- long double (64-bit on arm64 iOS, same as double) --------------------

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_long_double(char *first, char *last, long double value)
    __asm__("__ZNSt3__18to_charsEPcS0_e");

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_long_double(char *first, char *last, long double value) {
    return to_chars_double(first, last, static_cast<double>(value),
                           std::chars_format::general, -1, false);
}

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_long_double_fmt(char *first, char *last,
                                    long double value, std::chars_format fmt)
    __asm__("__ZNSt3__18to_charsEPcS0_eNS_12chars_formatE");

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_long_double_fmt(char *first, char *last,
                                    long double value, std::chars_format fmt) {
    return to_chars_double(first, last, static_cast<double>(value), fmt, -1,
                           false);
}

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_long_double_fmt_prec(char *first, char *last,
                                         long double value,
                                         std::chars_format fmt, int precision)
    __asm__("__ZNSt3__18to_charsEPcS0_eNS_12chars_formatEi");

extern "C" __attribute__((used)) std::to_chars_result
__amethyst_to_chars_long_double_fmt_prec(char *first, char *last,
                                         long double value,
                                         std::chars_format fmt, int precision) {
    return to_chars_double(first, last, static_cast<double>(value), fmt,
                           precision, true);
}
