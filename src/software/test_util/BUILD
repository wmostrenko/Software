package(default_visibility = ["//visibility:public"])

cc_library(
    name = "test_util",
    testonly = True,
    srcs = [
        "equal_within_tolerance.cpp",
        "test_util.cpp",
    ],
    hdrs = [
        "equal_within_tolerance.h",
        "test_util.h",
    ],
    deps = [
        "//proto:tbots_cc_proto",
        "//proto:tbots_nanopb_proto",
        "//proto/message_translation:tbots_protobuf",
        "//shared:constants",
        "//shared/test_util:tbots_gtest_main",
        "//software/ai/navigator/obstacle",
        "//software/geom:angle",
        "//software/geom:angular_velocity",
        "//software/geom:geom_constants",
        "//software/geom:point",
        "//software/geom:polygon",
        "//software/geom:stadium",
        "//software/geom:vector",
        "//software/geom/algorithms",
        "//software/logger",
        "//software/world",
        "//software/world:robot_state",
        "@eigen",
    ],
)

cc_library(
    name = "fake_clock",
    srcs = ["fake_clock.cpp"],
    hdrs = ["fake_clock.h"],
)

cc_test(
    name = "test_util_test",
    srcs = ["test_util_test.cpp"],
    deps = [
        ":test_util",
        "//shared/test_util:tbots_gtest_main",
    ],
)

cc_test(
    name = "equal_within_tolerance_test",
    srcs = ["equal_within_tolerance_test.cpp"],
    deps = [
        ":test_util",
        "//shared/test_util:tbots_gtest_main",
    ],
)

cc_test(
    name = "fake_clock_test",
    srcs = ["fake_clock_test.cpp"],
    deps = [
        ":fake_clock",
        "//shared/test_util:tbots_gtest_main",
    ],
)
