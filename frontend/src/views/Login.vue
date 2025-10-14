<template>
  <v-container fluid class="fill-height">
    <v-row justify="center" align="center">
      <v-col cols="12" sm="8" md="6" lg="4">
        <v-card class="elevation-12">
          <v-card-title class="text-center text-h4 py-4">
            Login
          </v-card-title>
          
          <v-card-text>
            <v-form @submit.prevent="handleLogin" ref="form" aria-labelledby="login-title">
              <h2 id="login-title" class="sr-only">Login form</h2>
              <v-text-field
                v-model="credentials.username"
                label="Username"
                prepend-inner-icon="mdi-account"
                variant="outlined"
                :rules="[rules.required]"
                required
                autocomplete="username"
                :aria-describedby="error ? 'login-error' : undefined"
              ></v-text-field>
              
              <v-text-field
                v-model="credentials.password"
                label="Password"
                prepend-inner-icon="mdi-lock"
                variant="outlined"
                type="password"
                :rules="[rules.required]"
                required
                autocomplete="current-password"
                :aria-describedby="error ? 'login-error' : undefined"
              ></v-text-field>
              
              <v-alert
                v-if="error"
                type="error"
                variant="tonal"
                class="mb-4"
                id="login-error"
              >
                {{ error }}
              </v-alert>
              
              <v-btn
                type="submit"
                color="primary"
                block
                size="large"
                :loading="loading"
                :disabled="loading"
              >
                Login
              </v-btn>
            </v-form>
          </v-card-text>
          
          <v-card-actions class="justify-center pb-4">
            <v-btn
              variant="text"
              to="/reset-password"
              color="primary"
            >
              Forgot Password?
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { useNotifyStore } from '@/store/notify'

const router = useRouter()
const authStore = useAuthStore()
const notify = useNotifyStore()

const form = ref(null)
const loading = ref(false)
const error = ref('')

const credentials = reactive({
  username: '',
  password: ''
})

const rules = {
  required: v => !!v || 'This field is required'
}

const handleLogin = async () => {
  const { valid } = await form.value.validate()
  
  if (!valid) return
  
  loading.value = true
  error.value = ''
  
  try {
    await authStore.login(credentials)
    const next = router.currentRoute.value.query.next || '/dashboard'
    notify.success(`Welcome${authStore.username ? `, ${authStore.username}` : ''}`)
    router.push(next)
  } catch (err) {
    error.value = err.message || 'Login failed. Please check your credentials.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.fill-height {
  min-height: 100vh;
}
</style> 