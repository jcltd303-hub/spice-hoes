package com.spicehoes.identity.backend

import android.content.Context
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import com.spicehoes.identity.ServiceState
import java.io.File
import java.security.MessageDigest

/**
 * Phase C runtime boundary. This class deliberately refuses to claim identity transfer
 * until a verified model artifact and the Ghost tensor/pre/post-processing contract are wired.
 * Generic ORT Android is CPU/reference execution; QNN arrives through a custom runtime in Phase D.
 */
class OnnxIdentityBackend(
    private val context: Context,
    private val manifest: ModelManifest,
) : IdentityBackend {
    private var env: OrtEnvironment? = null
    private var session: OrtSession? = null
    private var actualSha256: String? = null

    override fun initialize(progress: (ServiceState) -> Unit) {
        progress(ServiceState.RUNTIME_LOADING)
        env = OrtEnvironment.getEnvironment()

        progress(ServiceState.MODEL_LOADING)
        val model = File(context.filesDir, "models/" + manifest.fileName)
        require(model.isFile) { "model missing: " + model.absolutePath }
        actualSha256 = sha256(model)
        val expected = manifest.sha256
        require(expected != null) { "model SHA-256 is not approved in manifest" }
        require(actualSha256.equals(expected, ignoreCase = true)) { "model SHA-256 mismatch" }
        require(manifest.commercialUse) { "model has not passed commercial-use gate" }

        session = env!!.createSession(model.absolutePath, OrtSession.SessionOptions())
        progress(ServiceState.ACCELERATOR_INITIALIZING)
    }

    override fun selfTest() {
        check(session != null) { "ONNX session not initialized" }
        // Tensor-level self-test is enabled only when the approved Ghost graph contract is pinned.
        error("Ghost tensor contract not pinned; refusing false-ready backend")
    }

    override fun health() = BackendHealth(
        backend = "onnx",
        provider = "cpu-reference",
        accelerated = false,
        modelLoaded = session != null,
        modelId = manifest.id,
        modelSha256 = actualSha256,
        identityApplied = false,
    )

    override fun transfer(reference: ByteArray, target: ByteArray, options: TransferOptions): TransferResult {
        check(session != null) { "ONNX session not initialized" }
        error("Identity transfer unavailable until Ghost preprocessing/postprocessing is verified")
    }

    override fun close() {
        session?.close()
        session = null
        env = null
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(1024 * 1024)
            while (true) {
                val n = input.read(buffer)
                if (n <= 0) break
                digest.update(buffer, 0, n)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
