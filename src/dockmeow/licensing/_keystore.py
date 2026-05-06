"""RSA-2048 public key stored in three fragments.

The fragments are concatenated at runtime by LicenseVerifier._load_public_key().
Split point positions are randomised at keygen time to make static analysis harder.

IMPORTANT: This file contains the PUBLIC key only.
           The PRIVATE key (dockmeow_private.pem) must never enter this repository.
"""

# Populated by tools/generate_keypair.py at keygen time.
_kp1: bytes = b'-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAtaoIXg7bUFYCZS+4TeBJ\n7uQ1jyRVjK+eTPTJ84N0g2JLX/4c8BP2VphQYk9LwrSsOLwYWvbkIh0sgYjfoZMK\n85FmOT'  # noqa: E501
_kp2: bytes = b'Txc2iWxvnNgGWz5GaHcoWrCI1KWqDvcUU2zkulm/nIyR2Mql9hz2UY4073\nVv6IXIjfwpjCbK05/pyG5al1zbNqV4asAQSFdQgxiePmJTzfZOETE36b7qXqkOxq\ng4D6/e6gV7oyYSfc'  # noqa: E501
_kp3: bytes = b'9ZM3NByJPPynJS0cZL0cSd44oVL2sw+CVypAPseZtbRHBfSa\nIE5DED7EgIymanv6+nRuxW0XqkGkSdfNxdzx8+Hj7AxSyhpEQKOO0o484pSGw+nn\nbQIDAQAB\n-----END PUBLIC KEY-----\n'  # noqa: E501
