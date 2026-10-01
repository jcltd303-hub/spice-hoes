package com.spicehoes.identity.image

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import com.spicehoes.identity.Config
import com.spicehoes.identity.ErrorCode
import com.spicehoes.identity.ServiceException
import java.io.ByteArrayOutputStream

data class ImageInfo(val width: Int, val height: Int, val mime: String)

interface ImageInspector {
    /** Bounds-only decode + validation. Throws INVALID_IMAGE / IMAGE_TOO_LARGE. */
    fun inspect(bytes: ByteArray): ImageInfo

    /** Returns PNG bytes (input returned as-is when already PNG). */
    fun toPng(bytes: ByteArray): ByteArray
}

class AndroidImageInspector : ImageInspector {
    private val allowed = setOf("image/png", "image/jpeg", "image/webp")

    override fun inspect(bytes: ByteArray): ImageInfo {
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, o)
        val mime = o.outMimeType
        if (o.outWidth <= 0 || o.outHeight <= 0 || mime == null) {
            throw ServiceException(ErrorCode.INVALID_IMAGE, "image could not be decoded")
        }
        if (mime !in allowed) {
            throw ServiceException(ErrorCode.INVALID_IMAGE, "unsupported image format $mime")
        }
        if (maxOf(o.outWidth, o.outHeight) > Config.MAX_IMAGE_DIM) {
            throw ServiceException(
                ErrorCode.IMAGE_TOO_LARGE,
                "image ${o.outWidth}x${o.outHeight} exceeds ${Config.MAX_IMAGE_DIM}px limit",
            )
        }
        return ImageInfo(o.outWidth, o.outHeight, mime)
    }

    override fun toPng(bytes: ByteArray): ByteArray {
        if (inspect(bytes).mime == "image/png") return bytes
        val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
            ?: throw ServiceException(ErrorCode.INVALID_IMAGE, "image could not be decoded")
        val out = ByteArrayOutputStream()
        try {
            bmp.compress(Bitmap.CompressFormat.PNG, 100, out)
        } finally {
            bmp.recycle()
        }
        return out.toByteArray()
    }
}
