<template>
  <v-container fluid class="fill-height">
    <v-row justify="center" align="center">
      <v-col cols="12" sm="8" md="6" lg="4">
        <v-card class="elevation-12">
          <v-card-title class="text-center text-h4 py-4">
            Change Password
          </v-card-title>
          
          <v-card-text>
            <v-form @submit.prevent="handleChangePassword" ref="form" aria-labelledby="change-title">
              <h2 id="change-title" class="sr-only">Change password form</h2>
              <v-text-field
                v-model="passwords.old_password"
                label="Current Password"
                prepend-inner-icon="mdi-lock"
                variant="outlined"
                type="password"
                :rules="[rules.required]"
                required
                autocomplete="current-password"
                :aria-describedby="error ? 'change-error' : undefined"
              ></v-text-field>
              
              <v-text-field
                v-model="passwords.new_password1"
                label="New Password"
                prepend-inner-icon="mdi-lock-plus"
                variant="outlined"
                type="password"
                :rules="[rules.required, rules.minLength]"
                required
                autocomplete="new-password"
                :aria-describedby="error ? 'change-error' : undefined"
              ></v-text-field>
              
              <v-text-field
                v-model="passwords.new_password2"
                label="Confirm New Password"
                prepend-inner-icon="mdi-lock-check"
                variant="outlined"
                type="password"
                :rules="[rules.required, rules.passwordMatch]"
                required
                autocomplete="new-password"
                :aria-describedby="error ? 'change-error' : undefined"
              ></v-text-field>
              
              <v-alert
                v-if="error"
                type="error"
                variant="tonal"
                class="mb-4"
                id="change-error"
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
                Change Password
              </v-btn>
            </v-form>
          </v-card-text>
          
          <v-card-actions class="justify-center pb-4">
            <v-btn
              variant="text"
              to="/dashboard"
              color="primary"
            >
              Back to Dashboard
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
import { useNotifyStore } from '@/store/notify'

const router = useRouter()

const form = ref(null)
const loading = ref(false)
const error = ref('')
const success = ref('')
const notify = useNotifyStore()

const passwords = reactive({
  old_password: '',
  new_password1: '',
  new_password2: ''
})

const rules = {
  required: v => !!v || 'This field is required',
  minLength: v => v.length >= 8 || 'Password must be at least 8 characters',
  passwordMatch: v => v === passwords.new_password1 || 'Passwords do not match'
}

const handleChangePassword = async () => {
  const { valid } = await form.value.validate()
  
  if (!valid) return
  
  loading.value = true
  error.value = ''
  success.value = ''
  
  try {
    const response = await fetch('/api/users/auth/change-password/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Token ${localStorage.getItem('token')}`
      },
      body: JSON.stringify(passwords)
    })
    
    if (response.ok) {
      success.value = 'Password changed successfully!'
      try { notify.success('Password changed') } catch {}
      // Clear form
      passwords.old_password = ''
      passwords.new_password1 = ''
      passwords.new_password2 = ''
      form.value.reset()
    } else {
      const data = await response.json()
      error.value = data.error || 'Failed to change password'
    }
  } catch (err) {
    error.value = 'An error occurred while changing password'
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