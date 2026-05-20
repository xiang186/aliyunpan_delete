<template>
  <div class="login-container">
    <el-card class="login-card" shadow="always">
      <template #header>
        <div class="card-header">
          <el-icon size="32"><Cloudy /></el-icon>
          <h2>阿里云盘重复文件清理工具</h2>
        </div>
      </template>

      <p class="description">
        使用阿里云盘 App 扫描下方二维码登录，无需配置 OAuth 应用。
      </p>

      <!-- 二维码区域 -->
      <div class="qrcode-wrapper">
        <!-- 加载中 -->
        <div v-if="state === 'loading'" class="qrcode-placeholder">
          <el-icon class="loading-icon" size="40"><Loading /></el-icon>
          <p>正在生成二维码...</p>
        </div>

        <!-- 显示二维码 -->
        <div v-else-if="state === 'pending' || state === 'scaned'" class="qrcode-box">
          <img :src="qrDataUrl" alt="登录二维码" class="qrcode-img" />
          <div v-if="state === 'scaned'" class="scaned-overlay">
            <el-icon size="48" color="#67c23a"><CircleCheck /></el-icon>
            <p>已扫描，请在手机上确认</p>
          </div>
        </div>

        <!-- 已确认 -->
        <div v-else-if="state === 'confirmed'" class="qrcode-placeholder success">
          <el-icon size="48" color="#67c23a"><CircleCheck /></el-icon>
          <p>登录成功，正在跳转...</p>
        </div>

        <!-- 过期 / 取消 -->
        <div v-else-if="state === 'expired' || state === 'error'" class="qrcode-placeholder expired">
          <el-icon size="48" color="#f56c6c"><CircleClose /></el-icon>
          <p>{{ state === 'expired' ? '二维码已过期' : '加载失败' }}</p>
          <el-button type="primary" size="small" @click="loadQrcode">刷新二维码</el-button>
        </div>
      </div>

      <p class="hint">打开阿里云盘 App → 扫一扫</p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Cloudy, Loading, CircleCheck, CircleClose } from '@element-plus/icons-vue'
import QRCode from 'qrcode'
import { useAuthStore } from '@/stores/auth'
import { getQrcode, pollQrcode } from '@/api'

type QrState = 'loading' | 'pending' | 'scaned' | 'confirmed' | 'expired' | 'error'

const router = useRouter()
const authStore = useAuthStore()

const state = ref<QrState>('loading')
const qrDataUrl = ref('')
let qrData: Record<string, unknown> = {}
let qrCookies: Record<string, string> = {}
let pollTimer: ReturnType<typeof setInterval> | null = null
// QR codes expire after ~3 minutes; refresh after 2.5 min
const QR_EXPIRE_MS = 2.5 * 60 * 1000
let expireTimer: ReturnType<typeof setTimeout> | null = null

onMounted(async () => {
  if (authStore.isAuthenticated) {
    router.replace('/')
    return
  }
  await loadQrcode()
})

onUnmounted(() => {
  stopPolling()
})

async function loadQrcode() {
  stopPolling()
  state.value = 'loading'
  qrDataUrl.value = ''

  try {
    const res = await getQrcode()
    qrData = res.data.qr_data
    qrCookies = res.data.cookies
    qrDataUrl.value = await QRCode.toDataURL(res.data.qr_link, {
      width: 220,
      margin: 2,
      color: { dark: '#000000', light: '#ffffff' },
    })
    state.value = 'pending'
    startPolling()

    // Auto-refresh before expiry
    expireTimer = setTimeout(() => {
      if (state.value === 'pending' || state.value === 'scaned') {
        state.value = 'expired'
        stopPolling()
      }
    }, QR_EXPIRE_MS)
  } catch {
    state.value = 'error'
  }
}

function startPolling() {
  pollTimer = setInterval(async () => {
    try {
      const res = await pollQrcode(qrData, qrCookies)
      const { status, session_id, nickname } = res.data

      if (status === 'SCANED') {
        state.value = 'scaned'
      } else if (status === 'CONFIRMED' && session_id) {
        state.value = 'confirmed'
        stopPolling()
        authStore.setSession(session_id, res.data.user_id ?? null, nickname ?? null)
        setTimeout(() => router.replace('/'), 800)
      } else if (status === 'EXPIRED' || status === 'CANCELED') {
        state.value = 'expired'
        stopPolling()
      }
    } catch {
      // network error — keep polling
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (expireTimer !== null) {
    clearTimeout(expireTimer)
    expireTimer = null
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: #f5f7fa;
}

.login-card {
  width: 360px;
  text-align: center;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.description {
  color: #606266;
  font-size: 13px;
  margin-bottom: 20px;
  line-height: 1.6;
}

.qrcode-wrapper {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 240px;
}

.qrcode-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #909399;
  font-size: 14px;
}

.qrcode-placeholder.success {
  color: #67c23a;
}

.qrcode-placeholder.expired {
  color: #f56c6c;
}

.loading-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.qrcode-box {
  position: relative;
  display: inline-block;
}

.qrcode-img {
  display: block;
  width: 220px;
  height: 220px;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
}

.scaned-overlay {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.88);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 14px;
  color: #67c23a;
  font-weight: 500;
}

.hint {
  margin-top: 16px;
  font-size: 12px;
  color: #c0c4cc;
}
</style>
