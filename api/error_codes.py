class ErrorCodes:
    SUCCESS = (0, "Success")
    INVALID_INPUT = (1001, "Invalid input")
    ASS_GENERATION_FAILED = (2001, "ASS generation failed")
    ASS_STYLE_NOT_FOUND = (2002, "ASS style not found")
    USER_CANCELLED = (3001, "User cancelled")
    UNKNOWN_ERROR = (9999, "Unknown error")
    FFMPEG_RENDER_FAILED = (4001, "FFmpeg render failed")
