# ClearPass Sync Healthcheck Monitor for F5 BIG-IP

## Introduction

The `f5-cp-sync-check.py` script serves as an F5 external monitor, designed to verify the synchronization status of a whether a ClearPass node in an F5 resource pool is synchronized with the rest of the ClearPass cluster. This check goes above and beyond the recommended health checks proposed in the "Deploying CPPM with F5 BIG-IP Local Traffic Manager (LTM)" guide, which hasn't been updated since 2014. While ClearPass might function seamlessly concerning RADIUS and HTTPS operations, synchronization issues can surface due to server reboots or LAN/WAN outages, leading to problems authenticating guest accounts, registering devices, or other operations that are dependant on a synchronized cluster. To address this, this F5 external health monitor proactively flags ClearPass servers that have sync discrepancies. By employing this script, you gain a robust method to monitor the sync status of the ClearPass infrastructure, surpassing the monitoring capabilities of the Aruba recommended RADIUS and HTTPS monitors.

This README serves as a detailed guide on utilizing, deploying, and troubleshooting the ClearPass Sync Healthcheck Monitor script. The script executes an API call to the targeted server, inspecting the last replication timestamp to ascertain synchronization with the broader network. Its rigorous error-handling mechanisms ensure that a server is only recognized as "up" when synchronization is verified. Additionally, the script seamlessly manages OAuth tokens, and provides detailed logging.

## Intended Usage

This script and the monitor object it gets associated with are intended for use to monitor ClearPass nodes in a GTM/LTM resource pool where cluster synchronization is critical for their authentication purposes. Commonly, this would include any server which provides authentication service for Guest or Onboard users and devices, or any service that relies on an up-to-date Endpoint database. These are just examples, and there may be other use cases where synchronization is critical.

In some environments, it is possible that synchronization is not critical, and this script would not provide value. One such example would be a server which only provides 802.1X service which authenticates a user with Active Directory. If the service does not call any local databases on ClearPass (e.g., the Endpoint database) that are critical to update receive updates in near-real-time, it may not be relevant if the server is out of sync as it will not impact the authentication result.

## Requirements

1. **Timestamp Validation:** The script checks whether the replication timestamp is within the range of the F5. It's imperative that the F5 and ClearPass clocks are synchronized using NTP.
2. **API Client Creation:** As the script makes calls to the API, an API client needs to be set up on ClearPass. This client can be allocated an operator profile with minimal permissions to ensure security.
3. **Same Cluster:** It's assumed that all ClearPasses within the same pool belong to the same ClearPass cluster, as monitoring synchronization across different clusters wouldn't make much sense.

## Quick Setup

These steps are designed to quickly set up the healthcheck. Please note that this guide serves as a foundational reference only. You might need to adjust some settings depending on your security and monitoring requirements and preferences.

1. **Create API Client on ClearPass:**
    * Log into ClearPass Guest.
    * Navigate to `Administration > API Services > API Clients`.
    * Click on `Create API Client`.
        - Label the client in the `Client ID` field (Save this name for future reference). For instance: `F5_CP_SYNC_HEALTHCHECK`.
        - Ensure the `Enabled` option is checked.
        - Set the `Operating Mode` to `ClearPass REST API - this client will be utilized for API calls to ClearPass`.
        - Set `Operator Profile` to `Super Administrator` (You can refine this to a more restricted profile later on).
        - Choose `Grant Type: Client credentials`.
        - Store the `Client Secret` in a text editor for future use.
    * Click `Create API Client`.

2. **Import the Script:**
    * Download the `f5-cp-sync-check.py` file from this repository.
    * Access your BIG-IP interface.
    * Proceed to `System > File Management > External Monitor Program File List`.
    * Click `Import`.
        - Locate the `f5-cp-sync-check.py` file.
        - Assign a descriptive name to the file in the `Name` field (for example, you can set it to the filename for simplicity).
        - Click `Import`.

**3. Set Up the Monitor Object:**
    a. In BIG-IP, go to `Local Traffic > Monitors`.
    b. Click `Create`.
        i. Name your monitor, e.g., `ClearPass Sync`.
        ii. Define `Type` as `External`.
        iii. For `External Program`, select your script file (`f5-cp-sync-check.py` in this scenario).
        iv. Within `Variables`, type `CLIENT_ID` (remember it's case sensitive) for the Name. Use the API Client name you earlier set in ClearPass as the Value (e.g., `F5_CP_SYNC_HEALTHCHECK`), then press `Add`.
        v. For the next variable, type `CLIENT_SECRET` in the Name field. Paste the secret you saved from ClearPass in the `Value` section, then click `Add`.
        vi. If using a wildcard (0) port for pool members, switch `Configuration` from Basic to Advanced, then set the `Alias Service Port` to `443`.
        vii. Click `Finished`.

**4. Assign to Pool:**
    a. On BIG-IP, navigate to `Local Traffic > Virtual Servers > Pools`.
    b. Find and select your designated pool.
    c. Within the `Health Monitors` section, transfer your newly created monitor from the `Available` column to the `Active` column.
    d. Click `Update`.

## Advanced Configurations
### Operator Profile:
For optimal functioning of the ClearPass API client, the assigned operator profile should have the below permissions:
- **API Services**: Set to `Custom`
    * `Allow API Access`: Choose `Allow Access`.
- **Platform**: Set to `Custom`
    * `Import Configuration`: Set to `Read Only`.

No other permissions are required for the API Client operator profile.

### Monitor Configuration:

The default monitor configuration operates on a 5-second interval, a setting the script inherently assumes. However, if there's a need to modify the monitor interval, it's critical to define a variable called `MON_INTERVAL` that matches the desired interval. This adjustment is crucial as the script determines the freshness of the replication timestamp relative to the BIG-IP system time, but there is no mechanism for the script to determine the monitor interval automatically. Given that ClearPass refreshes the replication timestamp every 3 minutes, we allow for 3 minutes + the monitor interval + 5 seconds (a hard coded value to account for clock variances) to consider if a replication timestamp is new enough.

For example, if the monitor interval is 10 seconds, you should set `MON_INTERVAL` to 10, and a replication timestamp older than 3 minutes and 15 seconds will be considered invalid.

### Script Variables
- `CLIENT_SECRET`: Manditory. Client's secret key for API authentication. This will be visible in clear text in the current version of this script
- `CLIENT_ID`: Manditory. Client ID name for ClearPass API authentication.
- `BUFFER_TIME`: Time buffer for token refresh. 10 minutes by default if not specified. Must be less than token lifetime configured on the API client and greater than the monitor interval. Recommended minimum of 1 minute.
- `MON_INTERVAL`: Interval for monitoring in seconds. Must match the internal configured on the monitor itself. 5 seconds by default if not specified.

## Behavior and Error Detection
When the script loads, the script will look in its token file for an existing unexpired token. If a valid token is unavailable, a new token will be retrieved using OAuth.

The script then makes a call to the ClearPass server to retrieve the last replication timestamp for each node in the cluster. If the last replication timestamp of the ClearPass server in question is less than 10 seconds older than the highest replication timestamp in the cluster, and the highest replication timestamp is newer than 3 minutes, 5 seconds + MON_INTERVAL, the monitor will mark the node as UP.

The script will mark a node down for any of the following reasons:
- `HTTP error`: Seen for several reason:
    * Insufficient permissions on the API Client operator profile
    * Out of sync nodes that don't have the most recent tokens from the publisher
    * Tokens were invalidated due to changes on the API client
    * Either CLIENT_ID or CLIENT_SECRET are missing or invalid
- `URL Error`: Usually happens if the node hasn't started all of its services, or is hard down
- `Timeout`: Caused by lack of response for an HTTP request for a token or replication timestamp
- Unhandled reasons: Script fails to detect a known failure scenario

Log messages for errors and troubleshooting can be found in `/var/log/ltm`.

## Limitations
- The script does not handle encrypted client secrets currently. The client secret will be visible to anyone who can view the configuration, and will be bundled as part of a qkview and visible by F5 if uploaded to iHealth.
- If there's a change in token lifetime, the token file must be deleted manually. The token file is located in `/var/tmp/<name of monitor>-token.json`. Alternatively, you could wait for the token to expire, but this could take a long time.
- The BIG-IP only has python 2.7 available. Therefore, is not easy to import external modules.
- ClearPass only updates the Last Replication Timestamp once every 3 minutes. This implies that the maximum amount of time it potentially takes for a server to be marked `Down` is 3 minutes + the monitor timeout. This is unlikely, however, because the script marks a resource `Down` if it gets no HTTP response during the API calls, but it is worth noting. Therefore, make sure this isn't the only monitor in your resource pool.
- Updating the ClearPass infrastructure will cause databases to be out of sync for a while. It may make sense to disable the monitor in each ClearPass zone during a maintenance window so that the entire infrastructure doesn't get flagged as `Down` simultaneously.

## Troubleshooting
Check the `/var/log/ltm` logs for detailed information on script errors or issues. This is the most useful resource for checking why a node is failing its healthcheck. Use `tail -f /var/log/ltm` from the bash shell to watch logs in real time.

## About
The monitor has been tested on the following versions:
- BIG-IP 14.1.5.4
- ClearPass 6.9.13

### Version History
- Refer to the `CHANGELOG.md` file for a detailed version history.

### Disclaimer
This script is provided for the purpose of testing and troubleshooting, and is intended to be used in a responsible manner. It is not designed for, and should not be used for, unauthorized access to any systems. While efforts have been made to ensure its accuracy and reliability, the author and his employers assumes no responsibility for any issues or complications that may arise from the use of this script within your environment. Users are advised to carefully evaluate the script's applicability to their specific needs and to take appropriate precautions in its usage. This script is provided as-is without any warranties or guarantees. Use at your own discretion.

### License
This project is licensed under the MIT License. See the `LICENSE` file for more details.

### Author
Tim Haynie, CWNE #254, ACMX #508 [LinkedIn Profile](https://www.linkedin.com/in/timhaynie/)
