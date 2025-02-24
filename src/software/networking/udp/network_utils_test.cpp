#include "software/networking/udp/network_utils.h"

#include <gtest/gtest.h>

TEST(NetworkUtilsTest, getLocalIpValidInterface)
{
    std::string interface               = "lo";
    std::optional<std::string> local_ip = getLocalIp(interface, true);
    EXPECT_TRUE(local_ip);
    EXPECT_EQ(local_ip.value(), "127.0.0.1");
}

TEST(NetworkUtilsTest, getLocalIpInvalidInterface)
{
    std::string interface = "interfaceymcinterfaceface";
    EXPECT_FALSE(getLocalIp(interface, true));
}

TEST(NetworkUtilsTest, isIpv6Valid)
{
    std::string ip_address = "2001:0db8:85a3:0000:0000:8a2e:0370:7334";
    EXPECT_TRUE(isIpv6(ip_address));
}

TEST(NetworkUtilsTest, isIpv6ForIpv4)
{
    std::string ip_address = "127.0.0.1";
    EXPECT_FALSE(isIpv6(ip_address));
}

TEST(NetworkUtilsTest, isIpv6ForIpv4Mapped)
{
    // This is actually an IPv4 address mapped to an IPv6 address
    std::string ip_address = "::ffff:0:0";
    EXPECT_TRUE(isIpv6(ip_address));
}

TEST(NetworkUtilsTest, isIpv6ForLoopback)
{
    std::string ip_address = "::1";
    EXPECT_TRUE(isIpv6(ip_address));
}
