import sys

if sys.version_info >= (3, 10):
    # explicitly export for mypy
    from bisect import bisect_right as bisect_right
else:

    def bisect_right(a, x, lo=0, hi=None, *, key=None):
        if lo < 0:
            raise ValueError("lo must be non-negative")
        if hi is None:
            hi = len(a)
        if key is None:
            while lo < hi:
                mid = (lo + hi) // 2
                if x < a[mid]:
                    hi = mid
                else:
                    lo = mid + 1
        else:
            while lo < hi:
                mid = (lo + hi) // 2
                if x < key(a[mid]):
                    hi = mid
                else:
                    lo = mid + 1
        return lo
