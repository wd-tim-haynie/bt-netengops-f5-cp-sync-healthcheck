# ClearPass Sync Healthcheck Monitor for F5 BIG-IP

## Introduction

The `f5-cp-sync-check.py` script serves as an F5 external monitor designed to verify the synchronization status of a whether a ClearPass node in an F5 resource pool is synchronized with the rest of the ClearPass cluster. This check goes above and beyond the recommended health checks proposed in the "Deploying CPPM with F5 BIG-IP Local Traffic Manager (LTM)" guide, which hasn't been updated since 2014. While ClearPass might appear to function seamlessly concerning RADIUS and HTTPS operations, synchronization issues due to server reboots or LAN/WAN outages can lead to problems authenticating guest accounts, registering devices, or other operations that are dependant on a synchronized cluster.

To address this, this F5 external health monitor proactively removes ClearPass servers that have sync discrepancies from their associated resource pools. By employing this script, you gain a robust method to monitor the sync status of the ClearPass infrastructure, surpassing the monitoring capabilities of the Aruba recommended RADIUS and HTTPS monitors.

This README serves as a detailed guide on utilizing, deploying, and troubleshooting the ClearPass Sync Healthcheck Monitor script.

The mechanism to determine whether the node is in sync is straightforward. First, an API call is made to generate an OAuth token based on client credentials (client ID and secret). Once the token is received by the F5, the script sleeps for a configurable amount of time which represents the maximum allowed sync skew time. After the sleep time expires, the script makes a 2nd call using to check the status of its new token. If the 2nd API call is successful, the monitor will mark the node `Up`. Detailed logging and the ability to use an encrypted secret are configurable.

It is advisable to put a link to this repository in the description field of your monitor and the description field of the API client since this README is the only source of documentation for the monitor.

## Intended Usage

This script and the monitor object it gets associated with are intended for use to monitor ClearPass nodes in a GTM/LTM resource pool where cluster synchronization is critical for their authentication purposes. Commonly, this would include any server which provides authentication service for Guest or Onboard users and devices, or any service that relies on an up-to-date Endpoint database. These are just examples, and there may be other use cases where synchronization is critical.

In some environments, it is possible that synchronization is not critical, and this script would not provide value. If no services on the server refer to any local databases on ClearPass (e.g., the Endpoint database) that are critical to update receive updates in near-real-time, it may not be relevant if the server is out of sync as it will not impact the authentication result. One such example would be a server which only provides 802.1X service and authenticates a user against Active Directory using EAP-TLS, where the user certificates are signed and revocation status is maintained by a non-ClearPass CA.

## Requirements

1. **API Client Creation:** As the script makes calls to the API, an API client needs to be set up on ClearPass. This client can be allocated an operator profile with minimal permissions to ensure security.
2. **HTTPS communication:** The API calls are made using HTTPS over port 443. This will need to be allowed through any firewalls that sit between the F5 and ClearPass node.

## Quick Setup

These steps are designed to quickly set up the healthcheck. Please note that this section serves as a foundational reference only. You might need to adjust some settings depending on your security and monitoring requirements and preferences. See the `Advanced Configuration` section below for additional configuration options.

1. **Create API Client on ClearPass:**
    * Log into ClearPass Guest.
    * Navigate to `Administration > API Services > API Clients`.
    * Click on `Create API Client`.
        - Label the client in the `Client ID` field (Save this name for future reference). For instance: `F5_CP_SYNC_HEALTHCHECK`.
        - In the `Description` field, put a link to this repository as it is the only source of documentation for the monitor.
        - Ensure the `Enabled` option is checked.
        - Set the `Operating Mode` to `ClearPass REST API - this client will be utilized for API calls to ClearPass`.
        - Set `Operator Profile` to `Super Administrator` (You should refine this to a more restricted profile later on).
        - Choose `Grant Type: Client credentials`.
        - Store the `Client Secret` in a text editor for later. Treat this secret like you would any other password.
    * Click `Create API Client`.

2. **Import the Script:**
    * Download the `f5-cp-sync-check.py` file from this repository.
    * Access your BIG-IP interface.
    * Navigate to `System > File Management > External Monitor Program File List`.
    * Click `Import`.
        - Locate the `f5-cp-sync-check.py` file.
        - Assign a descriptive name to the file in the `Name` field (for example, you can set it to the filename for simplicity).
        - Click `Import`.

3. **Set Up the Monitor Object:**
    * On the BIG-IP, go to `Local Traffic > Monitors`.
    * Click `Create`.
        - Name your monitor, e.g., `ClearPass Sync`.
        - In the `Description` field, put a link to this repository as it is the only source of documentation for the monitor.
        - Set `Type` as `External`.
        - For `External Program`, select your script file (`f5-cp-sync-check.py` if you named it the same as the filename in the previous step).
        - For `Interval`, set 20.
        - For `Timeout`, set 120.
        - Within `Variables`, type `CLIENT_ID` for the Name. Use the API Client name you earlier set in ClearPass as the Value (e.g., `F5_CP_SYNC_HEALTHCHECK`), then press `Add`. Note that everything is case sensitive.
        - For the next variable, type `CLIENT_SECRET` in the Name field. Paste the secret you saved from ClearPass in the `Value` section, then click `Add`.
        - If using a wildcard (0) port for pool members, switch `Configuration` from `Basic` to `Advanced`, then set the `Alias Service Port` to `443`.
        - Click `Finished`.

4. **Assign to Pool:**
    * **Only do this step in a maintenance window for production devices**.
    * On the BIG-IP, navigate to `Local Traffic > Virtual Servers > Pools`.
    * Find and select your ClearPass pool.
    * Within the `Health Monitors` section, transfer your newly created monitor created in the previous step (`ClearPass Sync` was the example) from the `Available` column to the `Active` column.
    * Click `Update`.

## Advanced Configurations
### BIG-IP Monitor Configuration:
#### Monitor `Variables`
- `CLIENT_ID`: Mandatory. Client ID name for ClearPass API authentication.
- `CLIENT_SECRET`: Client's secret key for API authentication. This will be visible in clear text. It is recommended to use an encrypted secret instead. Mandatory if `ENCRYPTED_SECRET` is not used. 
- `ENCRYPTED_SECRET`: An aes-256-cbc encrypted version of the client secret. Mandatory if plaintext `CLIENT_SECRET` is not used. Requires `DECRYPTION_KEYFILE` to be set.
- `DECRYPTION_KEYFILE`: An iFile containing the decryption key which is used to decrypt the `ENCRYPTED_SECRET`. Manditory if plaintext `CLIENT_SECRET` is not used.
- `MAX_SKEW`: Optional, default 15.0 seconds. The maximum amount of time to consider the node to be in sync. The script will sleep this long before attempting to use its new token. Refer to the note in the `Additional Conderations` section for picking an appropriate `MAX_SKEW`.
- `TIMEOUT`: Optional, default 2.4 seconds. Maximum amount of time to wait for an HTTP response.
- `LOG_LEVEL`: Optional, default `CRITICAL`. Used to specific logging level severity to `/var/log/ltm`. Acceptable values are `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`.

#### Monitor `Interval`
The monitor `Interval` should be set to `MAX_SKEW` + 2x `TIMEOUT` + a small amount extra to account for time to initialize the script and network latency. If using all default configuration, set the interval to `20` (`MAX_SKEW` of 15.0s + 2x `TIMEOUT` 2.4s + 200ms to account for script init and latency).

#### Monitor `Timeout`
A good starting point for this monitor is `120` seconds for `Timeout`, but it is ultimately the administrator's decision how much time can be missed before the node should be marked `Down`. Typical F5 best practices say that this should be 3x the monitor `Interval` + 1 second, but this may not be a suitable value given the nature of this script. It is recommended that when this script is deployed, that `LOG_LEVEL` `ERROR` be set and monitored for a few days to make sure `Timeout` is neither too short nor too long.

#### Monitor `Description`
It is advisable to put a link to this repository in the description field of your monitor since this README is the only source of documentation for the monitor.

#### Monitor `Alias Service Port`
If your pool uses a wildcard (0) port for its members, you must assign the `Alias Service Port` as `443`. To set this value, you will need to switch the `Configuration` view from `Basic` to `Advanced`. You might see a warning when trying to change the monitor which reads `Cannot modify the address type of monitor /Common/<monitor name>` or a warning trying to assign the monitor to the pool which says `The monitor /Common/<monitor name> has a wildcard destination service and cannot be associated with a node that has a zero service.`.

### ClearPass API Client
#### Grant Type
Only "client credentials" are supported by the script.

#### Operator Profile
It would be a best security practice to implement a locked down operator profile to assign to the API client. See the `Operator Profile` section below.

#### Description
It is advisable to put a link to this repository in the description field of your API client since this README is the only source of documentation for the monitor.

#### Token Lifetime
It is best practice to set the token lifetime to match the monitor `Interval`. Setting it shorter can result in false negatives (monitor fails when it should have succeeded). The lifetime can be longer, but there is no need for this.

### Operator Profile:
The operator profile assigned to the API Client must have the below permissions:
- **API Services**: Set to `Custom`
    * `Allow API Access`: Choose `Allow Access`.

No other permissions are required for the API Client operator profile.

## Script Behavior
1. First, the script will check to see if both `ENCRYPTED_SECRET` and `DECRYPTION_KEY` are set. If so, the script will decrypt the client secret, and if not, the script will use a plaintext secret.
2. Once the secret is found, a starting time is recorded, and an OAuth request will be made using the client ID and secret as credentials.
3. When a token is returned, an end time is calculated to see how much time elapsed requesting the token.
4. The script will then sleep for `MAX_SKEW` minus the elapsed time above (if `MAX_SKEW` is 15.0s and it took 800ms to get the token, the script sleeps for 14.2 seconds).
5. After the sleep time, the script will then attempt to make a generic API call using the token. In the response we are expecting to find the Client ID. If this is found, the node is marked `Up`. If not, the script will log the failure in `/var/log/ltm` if `LOG_LEVEL` is at least set to `ERROR`.

It is important to note that the reason this check is valid is that the token that is returned to the F5 is not stored on the subscriber node until it is replicated during its standard batch replication. The rigorous error-handling mechanisms of the script ensure that a server is only recognized as `Up` when synchronization is verified within maximum allowed skew time.

## Secret Encryption
Using a plaintext secret is recommended only for initial setup and troubleshooting purposes. It is not recommended to use a plaintext secret long-term in production as this secret will be visible to F5 support if a qkview is uploaded. Once a plaintext secret is working correctly, follow these steps to switch to an encrypted secret.

First generate a random character decryption key at least 32 characters long. Save this to a text file, then upload it to your F5 as an iFile (`System > File Management > iFile List`). It is critical to give this file a highly unique name because iFiles get stored on the local file system with a randomized suffix (e.g., `my_key.key` becomes `:Common:my_key.key_64841_1`). The script will only select one match as there is no way to differentiate which match is correct if multiple are found.

Now, log into the bash shell of your F5 to run an OpenSSL command. It is recommended to do this on the F5 itself as it has been observed that a different system running OpenSSL may generate a different encrypted key.

Run the command `echo '<your secret>' | openssl enc -aes-256-cbc -base64 -k '<your key>'`. The output will be broken into two lines. Remove the blank line and use this as your `ENCRYPTED_SECRET`. Mind the single quotes around your secret and key.

To test the reverse of this process (decryption), run the command `echo '<your encrypted secret>' | openssl enc -aes-256-cbc -d -a -k '<your key>'`. The output should be your secret. This is the exact command used by the script.

Now set your `ENCRYPTED_SECRET` variable in the monitor to the OpenSSL output (blank line removed). Next, set the `DECRYPTION_KEYFILE` variable to the name of your iFile containing the key. Note that the automatically prepended `:Common:` prefix in the filename is already accounted for in the script, so do not specify this as part of the key file name. Simply match the iFile name that is visible in the UI.

## Troubleshooting
First, set `LOG_LEVEL` to `DEBUG`. Once set, check the `/var/log/ltm` logs for detailed information on script errors or issues. This is the most useful resource for checking why a node is failing its healthcheck. Use `tail -f /var/log/ltm` from the bash shell to watch logs in real time, or `cat /var/log/ltm` to see all logs since the logfile was last wiped. Note that the `/var/log/ltm` log is used even if the BIG-IP is not provisioned for LTM.

The script will mark a node `Down` for any of the following reasons:
- `HTTP error`: Seen for several reason:
    * Out of sync nodes that don't have the most recent tokens from the publisher (this is what we are trying to detect)
    * Tokens were invalidated due to changes on the API client
    * Either `CLIENT_ID` or `CLIENT_SECRET` are missing or invalid, or decryption of the encrypted secret produced the wrong result
- `URL Error`: Usually happens if the node hasn't started all of its services, or is hard down
- `Timeout`: Caused by lack of response for an HTTP request for a token or replication timestamp, and no ICMP message received to flag a `URL Error`
- `SSL Error`: Seen occassionally. Something went wrong trying to set up the HTTPS connection between the F5 and ClearPass.
- Unhandled reasons: Script fails to detect a known failure scenario

If troubleshooting an issue where a plaintext secret works, but the encrypted secret does not, run the command `echo '<your encrypted secret>' | openssl enc -aes-256-cbc -d -a -k '<your key>'` on the bash shell of the F5 itself to verify that the secret is being decrypted as expected. Note that if the secret was encrypted on a device other than one of your production F5s, the encrypted version may not be the same as if it was done on the F5. Refer to the `Secret Encryption` section for more details.

## Limitations
- A plaintext `CLIENT_SECRET` will be visible in plain text to anyone who can view the configuration, and will be bundled as part of a qkview and visible by F5 if uploaded to iHealth. Secret encryption is strongly recommended. Regardless, it is strongly recommended to set an Operator Profile with the minimum required permissions on the API client so that the secret cannot be used for any other purpose even if the secret is compromised.
- The BIG-IP only has python 2.7 available, and it is not easy to import external modules.

## Other Considerations
- Updating the ClearPass infrastructure will cause databases to be out of sync for a while. It may make sense to disable the monitor in each ClearPass zone during a maintenance window so that the entire infrastructure doesn't get flagged as `Down` simultaneously.
- Pick a meaningful value for `MAX_SKEW`. This means we have to consider factors like Batch Replication Interval and CoA delays (potentially other time sensitive pieces of ClearPass). If using the ClearPass default Batch Replication Interval of 5 seconds, a `MAX_SKEW` of 5 seconds or less would always fail. Some solutions also use CoA, and the timing of the CoA packet might be dependant on a synchronized node. As such, CoA delays might be over 2x the Batch Replication interval, and it would make sense to set the `MAX_SKEW` to match the CoA delay.
- Authentication failover behavior of the NADs should also be considered. Current versions of Mist Wi-Fi will failover to the next RADIUS server if the existing F5 Virtual Server IP goes down due to sync issues. Therefore, to prevent a complete outage, a last resort RADIUS IP should be configured which points to ClearPass directly. Make sure you understand what will happen to your NADs if this monitor starts marking your Virtual Servers `Down`, and have the appropriate failover configuration in place.

## Known Issues
* In our test environment, the 1.0 version of the script did not work as expected on a GTM-only BIG-IP.

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
