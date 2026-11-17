// Fallback definitions for libc++ exception classes whose vtable /
// typeinfo / what() live in the dylib as a "key function" (LLVM 19) and
// are therefore missing from iOS 15.8.8's libc++.1.dylib.
//
// Why this is needed: with _LIBCPP_DISABLE_AVAILABILITY (kept on
// purpose, see Natives/patch_mobilegl.py enable_availability()) MobileGL
// compiles against the iOS 15 deployment target, but the resulting
// libMobileGL.dylib fails to dlopen on iOS 15:
//
//     Symbol not found: __ZTINSt3__119bad_expected_accessIvEE
//     Expected in: '/usr/lib/libc++.1.dylib'
// (latestlog.txt, 2026-11-17 23:46:59, iPhone 7 Plus / iOS 15.8.8,
//  run #24 build, commit 64d74de. The to_chars shim from the previous
//  round already works: the new log has no to_chars error at all and
//  gets as far as JVM launch, Java 25 and SDL3 init before crashing
//  here, still at "Loading library OpenGL".)
//
// Root cause, from libc++ itself (libcxx/include/__expected/
// bad_expected_access.h, libcxx/include/__configuration/
// availability.h):
//   * std::__1::bad_expected_access<void> is _LIBCPP_EXPORTED_FROM_ABI
//     and its what() is the class's key function:
//     _LIBCPP_AVAILABILITY_HAS_BAD_EXPECTED_ACCESS_KEY_FUNCTION
//     (= _LIBCPP_INTRODUCED_IN_LLVM_19, iOS 18.4) decides whether
//     what() is defined out-of-line in the dylib. With
//     _LIBCPP_DISABLE_AVAILABILITY that macro is 1, so every TU that
//     uses std::expected assumes the dylib provides the vtable and
//     typeinfo and emits only an undefined reference to them.
//   * MobileGL uses std::expected<T, ResultInfo> in
//     MobileGL/MG_Util/ShaderTranspiler/Types.h:208
//     (Result = std::expected<T, ResultInfo>). The derived class
//     bad_expected_access<ResultInfo> *is* emitted locally (its
//     vtable/typeinfo are defined in libMobileGL.dylib), but its
//     typeinfo points at the base typeinfo and its vtable points at
//     the base what(), so the load still needs those two base symbols.
//
// What the run #24 .tipa actually references (nm on the real
// libMobileGL.dylib, ~/workspace/amethyst-run24/...trollstore.tipa):
//   bad_expected_access<void>: ONLY these two symbols are undefined
//     and have no local definition in the dylib:
//       __ZNKSt3__119bad_expected_accessIvE4whatEv   (what())
//       __ZTINSt3__119bad_expected_accessIvEE        (typeinfo)
//     Its vtable and destructors are never referenced, so they are
//     not provided here.
//   bad_optional_access: ALL FIVE symbols are undefined and have no
//     local definition. Its typeinfo/vtable are data symbols, bound
//     eagerly at load, so it would be the next dlopen failure after
//     bad_expected_access is fixed. It is included in this same shim
//     to avoid another 45-minute rebuild round for a symbol that is
//     already known to be missing:
//       __ZNKSt19bad_optional_access4whatEv
//       __ZNSt19bad_optional_accessD0Ev / D1Ev
//       __ZTISt19bad_optional_access / __ZTVSt19bad_optional_access
//     (Note the mangling: std::bad_optional_access lives in namespace
//     std directly, not std::__1, hence "St19..." not "NSt3__1...".)
//   bad_function_call: its typeinfo/vtable/name already have weak
//     local definitions in the dylib, only what() is undefined
//     (lazily bound, reached only if what() is actually called):
//       __ZNKSt3__117bad_function_call4whatEv
//     Provided here for the same reason.
//   std::format_error is NOT included: its typeinfo/vtable/name
//     already have weak local definitions and its what() is not
//     referenced, so the load does not need it.
//
// How the symbols are built (no <expected> / <optional> are included,
// so the availability key-function trap cannot reappear):
//   * typeinfo objects are built by hand as __cxxabiv1::
//     __si_class_type_info (single, non-virtual, public base
//     std::exception): { vtable pointer, name pointer, base typeinfo }.
//     The vtable pointer is the __si_class_type_info vtable symbol
//     + 16 (the Itanium address point); the base typeinfo is
//     std::exception's, both ancient symbols present in iOS 15's
//     libc++ (the run #24 dylib already references both).
//   * The bad_optional_access vtable is built by hand as
//     { offset-to-top 0, typeinfo, D1, D0, what } -- the standard
//     Itanium layout for a class derived from std::exception,
//     verified on Linux against a real std::exception-derived class
//     (vtable slots D1/D0/what, offset 0, typeinfo pointer).
//   * what() strings are implementation-defined; the ones used here
//     are libc++'s: "bad access to std::expected" (from the libc++
//     header itself), "bad optional access", "bad_function_call".
//   * D1 (complete destructor) does nothing: neither
//     bad_optional_access nor std::exception has any members.
//     D0 (deleting destructor) calls D1 and frees the object.
//   * All definitions use the to_chars/hash shim pattern:
//     extern "C" + __asm__() to force the libc++ mangled name, and
//     __attribute__((used)) so LTO (MOBILEGL_ENABLE_LTO=ON) cannot
//     discard symbols that nothing calls by their C++ name.
//
// What this does NOT do: if MobileGL code actually throws a
// bad_expected_access<ResultInfo> at runtime, the exception object
// itself is built by MobileGL's own (locally defined) derived-class
// vtable/typeinfo, which now resolve through this shim's base
// typeinfo/what(). That path has not been exercised on a device yet;
// the load-time fix is what this shim guarantees. The next missing
// symbol, if any, will be reported by the next latestlog.txt in the
// same way.
#include <cstddef>

// --- symbols referenced from the system libc++ (ancient, on iOS 15) ---

// Vtable of __cxxabiv1::__si_class_type_info.
extern "C" const char __amethyst_si_class_type_info_vtable[]
    __asm__("__ZTVN10__cxxabiv120__si_class_type_infoE");

// Typeinfo of std::exception.
extern "C" const char __amethyst_ti_exception[]
    __asm__("__ZTISt9exception");

// --- typeinfo name strings (typeinfo name = mangled class name) --------

extern "C" __attribute__((used)) const char
    __amethyst_zts_bad_expected_access_void[]
    __asm__("__ZTSNSt3__119bad_expected_accessIvEE") =
        "NSt3__119bad_expected_accessIvEE";

extern "C" __attribute__((used)) const char
    __amethyst_zts_bad_optional_access[]
    __asm__("__ZTSSt19bad_optional_access") = "St19bad_optional_access";

// --- bad_expected_access<void> ------------------------------------------
// Needed: what() + typeinfo only.

extern "C" __attribute__((used)) const char*
__amethyst_bad_expected_access_void_what(const void* /* this */)
    __asm__("__ZNKSt3__119bad_expected_accessIvE4whatEv");

extern "C" __attribute__((used)) const char*
__amethyst_bad_expected_access_void_what(const void* /* this */) {
    return "bad access to std::expected";
}

// __si_class_type_info: { vtable + 16, name, base typeinfo }.
// (Declaration with the asm label, then a plain definition: putting
// extern + an initializer on one line makes GCC warn.)
extern "C" const void* __amethyst_ti_bad_expected_access_void[]
    __asm__("__ZTINSt3__119bad_expected_accessIvEE");
__attribute__((used)) const void* __amethyst_ti_bad_expected_access_void[] = {
    (const void*)(__amethyst_si_class_type_info_vtable + 16),
    (const void*)__amethyst_zts_bad_expected_access_void,
    (const void*)__amethyst_ti_exception,
};

// --- bad_optional_access ------------------------------------------------
// Needed: what() + D1 + D0 + typeinfo + vtable.

extern "C" __attribute__((used)) void
__amethyst_bad_optional_access_d1(void* /* this */)
    __asm__("__ZNSt19bad_optional_accessD1Ev");

extern "C" __attribute__((used)) void
__amethyst_bad_optional_access_d1(void* /* this */) {
    // No members in bad_optional_access or in std::exception.
}

extern "C" __attribute__((used)) void
__amethyst_bad_optional_access_d0(void* self)
    __asm__("__ZNSt19bad_optional_accessD0Ev");

extern "C" __attribute__((used)) void
__amethyst_bad_optional_access_d0(void* self) {
    __amethyst_bad_optional_access_d1(self);
    ::operator delete(self);
}

extern "C" __attribute__((used)) const char*
__amethyst_bad_optional_access_what(const void* /* this */)
    __asm__("__ZNKSt19bad_optional_access4whatEv");

extern "C" __attribute__((used)) const char*
__amethyst_bad_optional_access_what(const void* /* this */) {
    return "bad optional access";
}

extern "C" const void* __amethyst_ti_bad_optional_access[]
    __asm__("__ZTISt19bad_optional_access");
__attribute__((used)) const void* __amethyst_ti_bad_optional_access[] = {
    (const void*)(__amethyst_si_class_type_info_vtable + 16),
    (const void*)__amethyst_zts_bad_optional_access,
    (const void*)__amethyst_ti_exception,
};

// Vtable: { offset-to-top 0, typeinfo, D1, D0, what }.
extern "C" const void* __amethyst_vt_bad_optional_access[]
    __asm__("__ZTVSt19bad_optional_access");
__attribute__((used)) const void* __amethyst_vt_bad_optional_access[] = {
    (const void*)0,
    (const void*)__amethyst_ti_bad_optional_access,
    (const void*)__amethyst_bad_optional_access_d1,
    (const void*)__amethyst_bad_optional_access_d0,
    (const void*)__amethyst_bad_optional_access_what,
};

// --- bad_function_call --------------------------------------------------
// Needed: what() only (typeinfo/vtable/name already have weak local
// definitions in the dylib).

extern "C" __attribute__((used)) const char*
__amethyst_bad_function_call_what(const void* /* this */)
    __asm__("__ZNKSt3__117bad_function_call4whatEv");

extern "C" __attribute__((used)) const char*
__amethyst_bad_function_call_what(const void* /* this */) {
    return "bad_function_call";
}
