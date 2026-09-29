package com.deepsleeptt.travelmemory.upload

import android.app.Activity
import android.content.ContentResolver
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private val executor = Executors.newSingleThreadExecutor()
    private val selected = mutableListOf<Uri>()
    private lateinit var serverField: EditText
    private lateinit var tokenField: EditText
    private lateinit var tripField: EditText
    private lateinit var selectionLabel: TextView
    private lateinit var uploadButton: Button
    private lateinit var progress: ProgressBar
    private lateinit var resultLabel: TextView
    private val pickerRequest = 42

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        setContentView(buildView())
    }

    private fun buildView(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 32, 40, 24)
        }
        fun label(text: String) = TextView(this).apply {
            this.text = text
            textSize = 14f
            setPadding(0, 14, 0, 6)
        }
        fun field(hint: String, value: String = "") = EditText(this).apply {
            this.hint = hint
            setText(value)
            singleLine = true
            setPadding(16, 10, 16, 10)
        }

        root.addView(TextView(this).apply {
            text = "行驿相册上传"
            textSize = 28f
            setTextColor(0xff111827.toInt())
        })
        root.addView(TextView(this).apply {
            text = "只选择并上传照片到指定行程"
            textSize = 15f
            setTextColor(0xff6b7280.toInt())
        })
        root.addView(label("服务地址"))
        serverField = field("例如 https://your-server.example", "http://10.0.2.2:4177")
        root.addView(serverField)
        root.addView(label("媒体令牌"))
        tokenField = field("Bearer 令牌")
        tokenField.inputType = 0x81
        root.addView(tokenField)
        root.addView(label("行程 ID"))
        tripField = field("规划模块生成的 tripId")
        root.addView(tripField)

        val choose = Button(this).apply {
            text = "选择照片"
            setOnClickListener { openPicker() }
        }
        root.addView(choose, LinearLayout.LayoutParams(-1, -2).apply { topMargin = 20 })
        selectionLabel = TextView(this).apply {
            text = "尚未选择照片"
            setTextColor(0xff4b5563.toInt())
            setPadding(0, 12, 0, 4)
        }
        root.addView(selectionLabel)
        uploadButton = Button(this).apply {
            text = "上传选中的照片"
            isEnabled = false
            setOnClickListener { uploadSelected() }
        }
        root.addView(uploadButton)
        progress = ProgressBar(this).apply { visibility = View.GONE }
        root.addView(progress, LinearLayout.LayoutParams(-1, 56).apply { gravity = Gravity.CENTER })
        resultLabel = TextView(this).apply {
            setTextColor(0xff374151.toInt())
            setPadding(0, 12, 0, 0)
        }
        root.addView(resultLabel)
        return root
    }

    private fun openPicker() {
        val intent = if (android.os.Build.VERSION.SDK_INT >= 33) {
            Intent("android.provider.action.PICK_IMAGES").apply {
                type = "image/*"
                putExtra("android.provider.extra.PICK_IMAGES_MAX", 100)
                putExtra("android.provider.extra.PICK_IMAGES_LAUNCH_TAB", 1)
            }
        } else {
            Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                type = "image/*"
                putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                addCategory(Intent.CATEGORY_OPENABLE)
            }
        }
        startActivityForResult(intent, pickerRequest)
    }

    @Suppress("DEPRECATION")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != pickerRequest || resultCode != RESULT_OK || data == null) return
        selected.clear()
        data.clipData?.let { clip ->
            for (index in 0 until clip.itemCount) selected.add(clip.getItemAt(index).uri)
        } ?: data.data?.let(selected::add)
        selectionLabel.text = if (selected.isEmpty()) "尚未选择照片" else "已选择 ${selected.size} 张照片"
        uploadButton.isEnabled = selected.isNotEmpty()
    }

    private fun uploadSelected() {
        val base = serverField.text.toString().trim().trimEnd('/')
        val token = tokenField.text.toString().trim()
        val tripId = tripField.text.toString().trim()
        if (base.isEmpty() || token.isEmpty() || tripId.isEmpty()) {
            Toast.makeText(this, "请填写服务地址、媒体令牌和行程 ID", Toast.LENGTH_SHORT).show()
            return
        }
        uploadButton.isEnabled = false
        progress.visibility = View.VISIBLE
        resultLabel.text = "正在上传…"
        executor.execute {
            var success = 0
            val errors = mutableListOf<String>()
            selected.forEachIndexed { index, uri ->
                try {
                    uploadOne(base, token, tripId, uri)
                    success++
                } catch (error: Exception) {
                    errors.add("第 ${index + 1} 张：${error.message ?: "失败"}")
                }
            }
            runOnUiThread {
                progress.visibility = View.GONE
                uploadButton.isEnabled = selected.isNotEmpty()
                resultLabel.text = "上传完成：成功 $success/${selected.size}" + if (errors.isEmpty()) "" else "\n${errors.joinToString("\n")}"
            }
        }
    }

    private fun uploadOne(base: String, token: String, tripId: String, uri: Uri) {
        val bytes = jpegBytes(uri)
        val connection = (URL("$base/api/media/photos").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 8_000
            readTimeout = 120_000
            doOutput = true
            setRequestProperty("Authorization", "Bearer $token")
            setRequestProperty("Content-Type", "image/jpeg")
            setRequestProperty("X-Trip-Id", tripId)
            capturedDay(uri)?.let { setRequestProperty("X-Captured-Day", it) }
        }
        connection.outputStream.use { it.write(bytes) }
        val code = connection.responseCode
        if (code !in 200..299) throw IllegalStateException("服务端返回 HTTP $code")
        connection.disconnect()
    }

    private fun jpegBytes(uri: Uri): ByteArray {
        val bitmap = contentResolver.openInputStream(uri).use { input -> BitmapFactory.decodeStream(input) }
            ?: throw IllegalStateException("无法读取照片")
        val scale = minOf(1f, 2560f / maxOf(bitmap.width, bitmap.height).toFloat())
        val resized = if (scale < 1f) Bitmap.createScaledBitmap(bitmap, (bitmap.width * scale).toInt(), (bitmap.height * scale).toInt(), true) else bitmap
        return ByteArrayOutputStream().use { output ->
            if (!resized.compress(Bitmap.CompressFormat.JPEG, 86, output)) throw IllegalStateException("无法转换 JPEG")
            if (resized !== bitmap) resized.recycle()
            output.toByteArray()
        }
    }

    private fun capturedDay(uri: Uri): String? {
        val date = contentResolver.query(uri, arrayOf(OpenableColumns.LAST_MODIFIED), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) cursor.getLong(0) else 0L
        } ?: 0L
        return if (date > 0) SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date(date)) else null
    }

    override fun onDestroy() {
        executor.shutdownNow()
        super.onDestroy()
    }
}
