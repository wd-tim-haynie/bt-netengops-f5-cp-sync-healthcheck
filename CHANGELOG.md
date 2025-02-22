# Changelog

* v2.1 2025-02-22: Added extra troubleshooting tips
* v2.1 2023-09-29: Fixed a bug relating to the TIMEOUT variable
* v2.0 2023-09-27: Changes the way sync is measured. No longer reads "Last Replication Timestamp" as this is unreliable. Instead generates a token, sleeps for the maximum allowed skew time, then tries to use the token. If using the token is successful, the node is in sync. Also adds encrypted secrets and configurable logging.
* v1.0 2023-09-23: Initial version. Deprecated.
