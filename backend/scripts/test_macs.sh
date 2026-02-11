#!/bin/bash
# MAC Verification Test Script
# Tests all MACs against Mac-Tracker API

API_URL="http://localhost:8001/api"

# Convert Huawei format (xxxx-xxxx-xxxx) to colon format (XX:XX:XX:XX:XX:XX)
huawei_to_colon() {
    local mac=$(echo "$1" | tr -d '-' | tr '[:upper:]' '[:lower:]')
    echo "${mac:0:2}:${mac:2:2}:${mac:4:2}:${mac:6:2}:${mac:8:2}:${mac:10:2}" | tr '[:lower:]' '[:upper:]'
}

# MAC list (Huawei format)
MACS="
0007-326d-6168
0018-6e2a-ddb7
0018-6e2a-ddb8
0018-6e2a-ddba
0018-6e2a-ddbb
0018-6e2a-ddbc
0018-6e2a-ddc2
0018-6e2a-ddcb
0018-6e2a-ddd9
0018-6e2a-de6b
0018-6e2a-df00
0018-6e2a-df01
0018-6e2a-df02
0018-6e2a-df03
0018-6e2a-df04
0018-6e2a-df06
0018-6e2a-df07
0018-6e2a-df0c
0040-c137-1272
0040-c137-1ac4
0040-c137-1b5e
0040-c137-88cd
0040-c13d-3d7d
0040-c13d-4db9
0040-c13d-4eb7
0040-c13d-4f77
0040-c13d-5017
0040-c13d-5029
0040-c13d-5030
0040-c13d-50ca
0040-c13d-e3bc
0040-c13d-e3bf
0040-c13d-e3c0
0040-c13d-e3c2
0040-c13d-e4b6
00e0-4b62-fb6b
00e0-4b63-006d
00e0-4b63-019c
00e0-4b63-025e
00e0-4b63-0261
00e0-4b6f-b9cd
00e6-0e65-52c0
00e6-0e65-5800
00e6-0e65-5840
00e6-0e65-5880
00e6-0e65-58c0
00e6-0e65-5900
00e6-0e65-5980
00e6-0e65-5a00
00e6-0e65-5a40
00e6-0e65-5ac0
00e6-0e65-5b00
00e6-0e65-5b40
00e6-0e65-6f40
00e6-0e65-71c0
00e6-0e65-7240
00e6-0e65-72c0
00e6-0e65-7380
00e6-0e65-7480
00e6-0e65-74c0
00e6-0e65-7580
00e6-0e65-75c0
00e6-0e66-42c0
9cb2-e8b8-521a
0080-9fab-95ee
0080-9fe1-e698
0080-9fe2-edef
0080-9fe4-3eb6
0080-9fe4-3ecc
0080-9fe4-3ecf
0080-9fe4-3fd3
0080-9fe4-4032
0080-9fe4-405f
0080-9fe4-4081
0080-9fe4-40ad
0080-9fe4-410f
0080-9fe4-411d
0080-9fe4-413e
0080-9fe8-7e4d
0003-ea11-b754
0024-7756-e29f
0024-7756-e2a2
0024-7756-e2c4
0080-64fe-b48d
00f1-f531-e5ae
244b-03ab-9ec9
24fb-e364-b21e
5838-7948-08c3
5838-7957-335c
5838-7959-2123
5838-7959-2127
5838-7959-2132
5838-7959-2180
7438-b7ff-ecbb
9038-0cbb-a61f
a4bb-6d8b-b81d
f018-98eb-31bb
0001-2e5b-7bc9
0001-2e5b-7bdc
0001-2e60-697c
0001-2e7c-7194
0001-2e7c-71aa
0001-2e7c-71b2
0001-2e7c-71b4
0001-2e7c-71b6
0001-2e7c-71be
0001-2e7c-71bf
0001-2e7c-71c1
0001-2e7c-71c2
0001-2e7c-740b
0001-2e7c-7465
0001-2e7c-74b7
0001-2e7c-74c3
0001-2e7c-74d5
0001-2e7c-74dc
0001-2e7c-74dd
0001-2e7c-7bb5
0001-2e7c-7bc4
0001-2e7c-7c25
0001-2e7c-7c2e
0001-2e7f-2b85
0001-2e87-a4b9
0007-326d-615a
0007-3271-8b00
0007-3271-e959
0023-244d-a9f2
0023-244d-e0d2
0023-24d0-9710
0080-91e9-0217
3ce1-a13e-ead1
0017-315a-b3e7
1407-0800-4b4b
1e2c-f802-bcab
2097-2755-a9c5
2e91-ae41-6001
4062-3111-d7de
448a-5bdd-f868
686d-bcc9-8e57
94c6-911b-64b4
96f5-e436-e17b
a044-b70b-775c
a28a-c0c4-dd40
a4bb-6d8b-bbdf
aaf9-1b84-0b5e
d89e-f38e-9773
f402-2346-0733
0023-244d-a670
3095-e340-b0d1
3095-e341-9e0c
3095-e341-a3f8
3095-e343-078a
3095-e343-07fa
3095-e343-0a53
3095-e343-91e9
3095-e343-91f8
3095-e343-9216
3095-e343-922d
3095-e343-924b
3095-e343-9255
3095-e343-925b
3095-e343-927c
3095-e343-9299
3095-e343-929a
3095-e343-929b
3095-e343-92a8
3095-e343-92bf
3095-e343-92cf
3095-e343-92da
3095-e343-92ef
3095-e343-93be
3095-e343-93bf
3095-e343-93c5
3095-e343-93f5
3095-e343-93f9
3095-e343-9410
3095-e343-9457
3095-e343-947c
3095-e343-94ab
3095-e343-94ad
3095-e343-94c9
3095-e343-94db
3095-e343-94f0
3095-e343-99d8
3095-e343-99e6
3095-e343-99eb
3095-e343-99f6
3095-e343-9a3e
3095-e343-9a45
3095-e343-9a49
3095-e343-9a4a
3095-e343-9a4c
3095-e343-9a51
3095-e343-9a63
3095-e343-9a65
3095-e343-9a6a
3095-e343-9a74
3095-e343-9a77
3095-e343-9a84
3095-e343-9a85
3095-e343-9a8b
3095-e343-9a92
3095-e343-9aca
3095-e343-9ad1
3095-e343-9ad5
3095-e343-9b19
3095-e343-9b2e
3095-e343-9bae
3095-e343-9bb0
3095-e343-9c27
3095-e343-9c2b
3095-e343-9c46
3095-e343-9c5e
3095-e343-9c6a
3095-e343-9c8a
3095-e343-9c8b
3095-e343-9c9c
3095-e343-9ca2
3095-e343-9ca4
3095-e343-9ca9
3095-e343-9caa
3095-e343-9cae
3095-e343-9caf
3095-e343-9cb5
3095-e343-9cc5
3095-e343-9cca
3095-e343-9cd0
3095-e343-9cd2
3095-e343-9cd3
3095-e343-9cea
3095-e343-9d90
3095-e343-9db1
b6d0-0402-0000
"

# Remove duplicates and empty lines
UNIQUE_MACS=$(echo "$MACS" | tr -s '\n' | sort -u | grep -v '^$')

echo "========================================"
echo "MAC ADDRESS VERIFICATION TEST"
echo "Started: $(date)"
echo "========================================"

total=0
found=0
not_found=0
uplink=0

# Output files
REPORT_FILE="/tmp/mac_test_report.txt"
NOT_FOUND_FILE="/tmp/mac_not_found.txt"
FOUND_FILE="/tmp/mac_found.txt"
UPLINK_FILE="/tmp/mac_uplink.txt"

> "$REPORT_FILE"
> "$NOT_FOUND_FILE"
> "$FOUND_FILE"
> "$UPLINK_FILE"

echo "MAC_HUAWEI,MAC_COLON,STATUS,SWITCH,PORT,VLAN,IS_UPLINK" > "$REPORT_FILE"

for mac_hw in $UNIQUE_MACS; do
    ((total++))
    mac_colon=$(huawei_to_colon "$mac_hw")

    # Query API
    result=$(curl -s "${API_URL}/macs?q=${mac_colon}" 2>/dev/null)
    count=$(echo "$result" | grep -o '"total":[0-9]*' | grep -o '[0-9]*')

    if [ -z "$count" ] || [ "$count" -eq 0 ]; then
        ((not_found++))
        echo "$mac_hw,$mac_colon,NOT_FOUND,,,," >> "$REPORT_FILE"
        echo "$mac_hw" >> "$NOT_FOUND_FILE"
        printf "[%3d] %-17s -> NOT FOUND\n" "$total" "$mac_hw"
    else
        # Parse first result
        switch=$(echo "$result" | grep -o '"switch_hostname":"[^"]*"' | head -1 | cut -d'"' -f4)
        port=$(echo "$result" | grep -o '"port_name":"[^"]*"' | head -1 | cut -d'"' -f4)
        vlan=$(echo "$result" | grep -o '"vlan_id":[0-9]*' | head -1 | grep -o '[0-9]*')
        is_uplink=$(echo "$result" | grep -o '"is_uplink":[a-z]*' | head -1 | grep -o 'true\|false')

        if [ "$is_uplink" == "true" ]; then
            ((uplink++))
            echo "$mac_hw,$mac_colon,UPLINK,$switch,$port,$vlan,$is_uplink" >> "$REPORT_FILE"
            echo "$mac_hw -> $switch:$port" >> "$UPLINK_FILE"
            printf "[%3d] %-17s -> UPLINK %s:%s\n" "$total" "$mac_hw" "$switch" "$port"
        else
            ((found++))
            echo "$mac_hw,$mac_colon,ENDPOINT,$switch,$port,$vlan,$is_uplink" >> "$REPORT_FILE"
            echo "$mac_hw -> $switch:$port (VLAN $vlan)" >> "$FOUND_FILE"
            printf "[%3d] %-17s -> ENDPOINT %s:%s (VLAN %s)\n" "$total" "$mac_hw" "$switch" "$port" "$vlan"
        fi
    fi
done

echo ""
echo "========================================"
echo "SUMMARY"
echo "========================================"
echo "Total MACs tested:     $total"
echo "Found as ENDPOINT:     $found"
echo "Found on UPLINK:       $uplink"
echo "NOT FOUND in DB:       $not_found"
echo ""
echo "Report saved to: $REPORT_FILE"
echo "Not found list:  $NOT_FOUND_FILE"
echo "Found list:      $FOUND_FILE"
echo "Uplink list:     $UPLINK_FILE"
