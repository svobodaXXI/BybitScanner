"""Project signal-analysis package (``signal.quality``, ``signal.filter``) that is also a complete
standard-library ``signal``.

Every ``python -m ...`` run from the repository root puts the root ahead of the standard library on
``sys.path``, so ``import signal`` -- including the one inside ``subprocess``, ``multiprocessing``
and ``asyncio`` -- resolves to this package. On Windows that went unnoticed; on Linux the process
code needs ``signal.SIGTERM``, ``signal.SIGINT`` and friends (the multiprocessing resource tracker
reads them at import, ``Process.terminate()`` and ``Popen.terminate()`` send them), which an empty
package lacks. So this package re-exports the standard module's public API, loaded from the
standard library under a private name, while its own submodules keep working unchanged.
"""

import importlib.util as _importlib_util
import os as _os
import sys as _sys
import sysconfig as _sysconfig

_STANDARD_NAME = "_bybitscanner_standard_signal"


def _load_standard_signal():
    module = _sys.modules.get(_STANDARD_NAME)
    if module is not None:
        return module
    path = _os.path.join(_sysconfig.get_path("stdlib"), "signal.py")
    if _os.path.isfile(path):
        spec = _importlib_util.spec_from_file_location(_STANDARD_NAME, path)
        module = _importlib_util.module_from_spec(spec)
        _sys.modules[_STANDARD_NAME] = module    # signal.py's enum conversion looks itself up here
        try:
            spec.loader.exec_module(module)
        except BaseException:
            _sys.modules.pop(_STANDARD_NAME, None)
            raise
        return module
    import _signal                               # no source stdlib: the C core has the same API
    return _signal


for _name, _value in vars(_load_standard_signal()).items():
    if not _name.startswith("__"):
        globals().setdefault(_name, _value)
del _name, _value
