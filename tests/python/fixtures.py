"""Captured / representative OS command output used by the parser tests.

MAC addresses use the locally-administered 02:… range or documentation values.
"""

NETSH_IFACE_CONNECTED_RSSI = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6E AX211 160MHz
    GUID                   : 3f2b8a51-0000-0000-0000-000000000000
    Physical address       : 02:11:22:33:44:55
    Interface type         : Primary
    State                  : connected
    SSID                   : Home: Upstairs
    AP BSSID               : 02:aa:bb:cc:dd:01
    Band                   : 5 GHz
    Channel                : 44
    Network type           : Infrastructure
    Radio type             : 802.11ax
    Authentication         : WPA2-Personal
    Cipher                 : CCMP
    Connection mode        : Auto Connect
    Receive rate (Mbps)    : 1201
    Transmit rate (Mbps)   : 960
    Signal                 : 88%
    Rssi                   : -52
    Profile                : Home: Upstairs
    QoS MSCS Configured         : 0
    QoS Map Configured          : 0
    QoS Map Allowed by Policy   : 0

    Hosted network status  : Not available
"""

NETSH_IFACE_CONNECTED_PCT_ONLY = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Realtek 8821CE Wireless LAN 802.11ac PCI-E NIC
    GUID                   : 00000000-0000-0000-0000-000000000000
    Physical address       : 02:11:22:33:44:56
    State                  : connected
    SSID                   : CafeNet
    BSSID                  : 02:aa:bb:cc:dd:02
    Network type           : Infrastructure
    Radio type             : 802.11n
    Authentication         : WPA2-Personal
    Cipher                 : CCMP
    Connection mode        : Profile
    Channel                : 6
    Receive rate (Mbps)    : 72.2
    Transmit rate (Mbps)   : 72.2
    Signal                 : 60%
    Profile                : CafeNet

    Hosted network status  : Not available
"""

NETSH_IFACE_TWO = """
There are 2 interfaces on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX201
    GUID                   : 00000000-0000-0000-0000-000000000001
    Physical address       : 02:11:22:33:44:57
    State                  : disconnected
    Radio status           : Hardware On
                             Software On

    Name                   : Wi-Fi 2
    Description            : USB Wireless Adapter
    GUID                   : 00000000-0000-0000-0000-000000000002
    Physical address       : 02:11:22:33:44:58
    State                  : connected
    SSID                   : Office
    AP BSSID               : 02:aa:bb:cc:dd:03
    Band                   : 2.4 GHz
    Channel                : 11
    Radio type             : 802.11n
    Authentication         : WPA3-Personal
    Receive rate (Mbps)    : 144
    Transmit rate (Mbps)   : 144
    Signal                 : 40%
    Profile                : Office
"""

NETSH_IFACE_GERMAN = """
Es ist 1 Schnittstelle auf dem System vorhanden:

    Name                   : WLAN
    Beschreibung           : Intel(R) Wi-Fi 6 AX201
    Status                 : Verbunden
    SSID                   : Zuhause
    Signal                 : 90%
"""

NETSH_NO_WIRELESS = "There is no wireless interface on the system.\n"

NETSH_LOCATION_DENIED = """
Network shell commands need location permission to access WLAN information. Turn on Location services on the Location page in Privacy & security settings.

Here is the URI for the Location page in the Settings app:
ms-settings:privacy-location
"""

NETSH_NETWORKS = """
Interface name : Wi-Fi
There are 3 networks currently visible.

SSID 1 : Home: Upstairs
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP
    BSSID 1                 : 02:aa:bb:cc:dd:01
         Signal             : 88%
         Radio type         : 802.11ax
         Band               : 5 GHz
         Channel            : 44
         Bss Load:
             Connected Stations:        3
             Channel Utilization:       25 (9 %)
             Medium Available Capacity: 31250
         Basic rates (Mbps) : 6 12 24
         Other rates (Mbps) : 9 18 36 48 54
    BSSID 2                 : 02:aa:bb:cc:dd:11
         Signal             : 30%
         Radio type         : 802.11ax
         Band               : 2.4 GHz
         Channel            : 1
         Basic rates (Mbps) : 1 2 5.5 11
         Other rates (Mbps) : 6 9 12 18 24 36 48 54

SSID 2 :
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP
    BSSID 1                 : 02:aa:bb:cc:dd:21
         Signal             : 50%
         Radio type         : 802.11ac
         Band               : 5 GHz
         Channel            : 149

SSID 3 : <script>alert(1)</script>
    Network type            : Infrastructure
    Authentication          : Open
    Encryption              : None
    BSSID 1                 : 02:aa:bb:cc:dd:31
         Signal             : 100%
         Radio type         : 802.11be
         Band               : 6 GHz
         Channel            : 37
"""

NMCLI_AP_LIST = r"""*:Home\: Upstairs:02\:AA\:BB\:CC\:DD\:01:44:5220 MHz:540 Mbit/s:82:WPA2:wlp2s0
 ::02\:AA\:BB\:CC\:DD\:21:149:5745 MHz:270 Mbit/s:47:WPA2 WPA3:wlp2s0
 :Cafe:02\:AA\:BB\:CC\:DD\:31:6:2437 MHz:54 Mbit/s:30:--:wlp2s0
 :SixE:02\:AA\:BB\:CC\:DD\:41:37:6135 MHz:1200 Mbit/s:65:WPA3:wlp2s0
"""

NMCLI_DEVICE_STATUS = """wlp2s0:wifi:connected:Home\\: Upstairs
enp3s0:ethernet:unavailable:
lo:loopback:connected (externally):lo
p2p-dev-wlp2s0:wifi-p2p:disconnected:
"""

IW_LINK = """Connected to 02:aa:bb:cc:dd:01 (on wlp2s0)
\tSSID: Home: Upstairs
\tfreq: 5220.0
\tRX: 123456 bytes (789 packets)
\tTX: 23456 bytes (123 packets)
\tsignal: -57 dBm
\trx bitrate: 866.7 MBit/s VHT-MCS 9 80MHz short GI VHT-NSS 2
\ttx bitrate: 650.0 MBit/s VHT-MCS 7 80MHz short GI VHT-NSS 2
"""

SYSTEM_PROFILER_JSON = """{
  "SPAirPortDataType" : [
    {
      "spairport_airport_interfaces" : [
        {
          "_name" : "en0",
          "spairport_current_network_information" : {
            "_name" : "<redacted>",
            "spairport_network_channel" : "44 (5GHz, 80MHz)",
            "spairport_network_phymode" : "802.11ax",
            "spairport_network_rate" : 864,
            "spairport_security_mode" : "spairport_security_mode_wpa2_personal",
            "spairport_signal_noise" : "-55 dBm / -94 dBm"
          },
          "spairport_airport_other_local_wireless_networks" : [
            {
              "_name" : "Neighbour",
              "spairport_network_channel" : "6 (2GHz, 20MHz)",
              "spairport_network_phymode" : "802.11n",
              "spairport_security_mode" : "spairport_security_mode_wpa3_personal",
              "spairport_signal_noise" : "-78 dBm / -92 dBm"
            }
          ],
          "spairport_status_information" : "spairport_status_connected"
        },
        { "_name" : "awdl0", "spairport_status_information" : "spairport_status_connected" }
      ]
    }
  ]
}"""

AIRPORT_I = """     agrCtlRSSI: -61
     agrExtRSSI: 0
    agrCtlNoise: -92
    agrExtNoise: 0
          state: running
        op mode: station
     lastTxRate: 300
        maxRate: 300
lastAssocStatus: 0
    802.11 auth: open
      link auth: wpa2-psk
          BSSID: 2:aa:bb:cc:dd:1
           SSID: OldMac
            MCS: 15
        channel: 149,80
"""

ROUTE_PRINT_WIN = """===========================================================================
Interface List
 11...02 9a 0c 1e 07 f2 ......USB Ethernet Adapter
  1...........................Software Loopback Interface 1
===========================================================================

IPv4 Route Table
===========================================================================
Active Routes:
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0      192.168.1.1     192.168.1.10    291
          0.0.0.0          0.0.0.0         10.0.0.1        10.0.0.42     25
===========================================================================
Persistent Routes:
  Network Address          Netmask  Gateway Address  Metric
          0.0.0.0          0.0.0.0      192.168.1.1  Default
===========================================================================
"""

PROC_NET_ROUTE = """Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT
wlp2s0\t00000000\t0101A8C0\t0003\t0\t0\t600\t00000000\t0\t0\t0
wlp2s0\t0001A8C0\t00000000\t0001\t0\t0\t600\t00FFFFFF\t0\t0\t0
"""

ROUTE_GET_MAC = """   route to: default
destination: default
       mask: default
    gateway: 192.168.0.1
  interface: en0
      flags: <UP,GATEWAY,DONE,STATIC,PRCLONING,GLOBAL>
"""

PING_WIN_EN = """
Pinging 192.168.1.1 with 32 bytes of data:
Reply from 192.168.1.1: bytes=32 time=3ms TTL=64
Reply from 192.168.1.1: bytes=32 time<1ms TTL=64
Request timed out.
Reply from 192.168.1.1: bytes=32 time=12ms TTL=64

Ping statistics for 192.168.1.1:
    Packets: Sent = 4, Received = 3, Lost = 1 (25% loss),
Approximate round trip times in milli-seconds:
    Minimum = 0ms, Maximum = 12ms, Average = 5ms
"""

PING_WIN_DE = """
Ping wird ausgeführt für 192.168.1.1 mit 32 Bytes Daten:
Antwort von 192.168.1.1: Bytes=32 Zeit=4ms TTL=64
Antwort von 192.168.1.1: Bytes=32 Zeit=5ms TTL=64

Ping-Statistik für 192.168.1.1:
    Pakete: Gesendet = 2, Empfangen = 2, Verloren = 0
Ca. Zeitangaben in Millisek.:
    Minimum = 4ms, Maximum = 5ms, Mittelwert = 4ms
"""

PING_LINUX = """PING 192.168.1.1 (192.168.1.1) 56(84) bytes of data.
64 bytes from 192.168.1.1: icmp_seq=1 ttl=64 time=2.31 ms
64 bytes from 192.168.1.1: icmp_seq=2 ttl=64 time=1.95 ms
64 bytes from 192.168.1.1: icmp_seq=3 ttl=64 time=3.40 ms

--- 192.168.1.1 ping statistics ---
4 packets transmitted, 3 received, 25% packet loss, time 1503ms
rtt min/avg/max/mdev = 1.950/2.553/3.400/0.614 ms
"""

# Real output format from a Realtek USB adapter on Windows 11 (identifiers anonymised).
NETSH_IFACE_REALTEK = """
There is 1 interface on the system:

    Name                   : Wi-Fi 2
    Description            : Realtek RTL8192EU Wireless LAN 802.11n USB 2.0 Network Adapter
    GUID                   : 00000000-0000-0000-0000-000000000003
    Physical address       : 02:47:d7:00:00:93
    Interface type         : Primary
    State                  : connected
    SSID                   : Home_Room
    AP BSSID               : 02:f1:96:00:65:cd
    Band                   : 2.4 GHz
    Channel                : 1
    Connected Akm-cipher   : [ akm = 00-0f-ac:02, cipher =  00-0f-ac:04 ]
    Network type           : Infrastructure
    Radio type             : 802.11n
    Authentication         : WPA2-Personal
    Cipher                 : CCMP
    Connection mode        : Profile
    Receive rate (Mbps)    : 144.4
    Transmit rate (Mbps)   : 144.4
    Signal                 : 84% 
    Rssi                   : -44
    Profile                : Home_Room 
    QoS MSCS Configured         : 0
    QoS Map Configured          : 0
    QoS Map Allowed by Policy   : 0
"""
