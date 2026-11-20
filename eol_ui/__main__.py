from eol_ui.app_log import prepare_streams

prepare_streams()

from eol_ui.app import main  # noqa: E402

raise SystemExit(main())
