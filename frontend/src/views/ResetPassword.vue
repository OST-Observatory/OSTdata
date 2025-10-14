<template>
  <v-container fluid class="fill-height">
    <v-row justify="center" align="center">
      <v-col cols="12" sm="8" md="6" lg="4">
        <v-card class="elevation-12">
          <v-card-title class="text-center text-h4 py-4">
            Reset Password
          </v-card-title>
          
          <v-card-text>
            <v-form @submit.prevent="handleResetPassword" ref="form" aria-labelledby="reset-title">
              <h2 id="reset-title" class="sr-only">Reset password form</h2>
              <v-text-field
                v-model="email"
                label="Email Address"
                prepend-inner-icon="mdi-email"
                variant="outlined"
                type="email"
                :rules="[rules.required, rules.email]"
                required
                autocomplete="email"
                :aria-describedby="error ? 'reset-error' : undefined"
              ></v-text-field>
              
              <v-alert
                v-if="error"
                type="error"
                variant="tonal"
                class="mb-4"
                id="reset-error"
              >
                {{ error }}
              </v-alert>
              
              <!-- Success handled via toast -->
              
              <v-btn
                type="submit"
                color="primary"
                block
                size="large"
                :loading="loading"
                :disabled="loading"
              >
                Send Reset Link
              </v-btn>
            </v-form>
          </v-card-text>
          
          <v-card-actions class="justify-center pb-4">
            <v-btn
              variant="text"
              to="/login"
              color="primary"
            >
              Back to Login
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
import { ref } from 'vue'
import { useNotifyStore } from '@/store/notify'

const form = ref(null)
const loading = ref(false)
const error = ref('')
const success = ref('')
const notify = useNotifyStore()
const email = ref('')

const rules = {
  required: v => !!v || 'This field is required',
  email: v => /.+@.+\..+/.test(v) || 'Please enter a valid email address'
}

const handleResetPassword = async () => {
  const { valid } = await form.value.validate()
  
  if (!valid) return
  
  loading.value = true
  error.value = ''
  success.value = ''
  
  try {
    const response = await fetch('/api/users/auth/reset-password/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ email: email.value })
    })
    
    if (response.ok) {
      success.value = 'Password reset link has been sent to your email address.'
      try { notify.success('Reset link sent') } catch {}
      email.value = ''
      form.value.reset()
    } else {
      const data = await response.json()
      error.value = data.error || 'Failed to send reset link'
    }
  } catch (err) {
    error.value = 'An error occurred while sending reset link'
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