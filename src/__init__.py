try:
    # Use the Windows certificate store for HTTPS (needed on networks that inspect HTTPS traffic).
    # Certificate verification stays ON.
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass
