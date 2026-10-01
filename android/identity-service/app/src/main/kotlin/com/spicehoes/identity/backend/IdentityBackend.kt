package com.spicehoes.identity.backend

import com.spicehoes.identity.ServiceState

data class BackendHealth(
    val backend: String,
    val provider: String,
    /** Only true after an accelerated provider has initialized AND run inference successfully. */
    val accelerated: Boolean,
    val modelLoaded: Boolean,
    val modelId: String,
    val modelSha256: String?,
    /** False for passthrough/mock backends: the output is NOT identity-consistent. */
    val identityApplied: Boolean,
)

data class TransferOptions(val preserveComposition: Boolean)

data class TransferResult(val imageBytes: ByteArray)

/**
 * Backend abstraction (spec section 11). HTTP, preprocessing and diagnostics must not
 * depend on a specific model or runtime.
 */
interface IdentityBackend {
    /** Report progress through the startup states; throws ServiceException on failure. */
    fun initialize(progress: (ServiceState) -> Unit)

    /** Run a known input through the backend (spec section 27). */
    fun selfTest()

    fun health(): BackendHealth

    fun transfer(reference: ByteArray, target: ByteArray, options: TransferOptions): TransferResult

    fun close()
}
