_in_hypofuzz_run: bool = False


def in_hypofuzz_run() -> bool:
    """
    |in_hypofuzz_run| returns ``True`` when HypoFuzz has been invoked via
    ``hypothesis fuzz`` or another entrypoint, and ``False`` otherwise. You can
    use this to check whether HypoFuzz is currently fuzzing (or about to
    start fuzzing), as opposed to just having been imported.
    """

    # this is a function to get ahead of any issues with importing
    # in_hypofuzz_run and then not receiving updates of hypofuzz setting it to a
    # different value, unlike `import hypofuzz; hypofuzz.detection.in_hypofuzz_run`.
    return _in_hypofuzz_run
