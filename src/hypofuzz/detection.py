#: |in_hypofuzz_run| is ``True`` when HypoFuzz has been invoked via
#: ``hypothesis fuzz`` or another entrypoint, and ``False`` otherwise. You can
#: use this to check whether HypoFuzz is currently fuzzing (or about to
#: start fuzzing).
in_hypofuzz_run: bool = False
