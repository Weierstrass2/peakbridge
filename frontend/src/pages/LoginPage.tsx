import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import { login } from '../services/authApi';
import { useAuthStore } from '../store/authStore';
import { isMockMode } from '../config/env';

export default function LoginPage() {
  const [email, setEmail] = useState('admin@peakbridge.com');
  const [password, setPassword] = useState('admin1234');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      console.log('🔐 Trying to login with:', email);
      const response = await login(email, password);
      console.log('✅ Login response:', response);
      const { access_token, user } = response;
      setAuth(access_token, user);
      console.log('🔑 Auth store updated with token:', access_token ? access_token.substring(0, 20) + '...' : 'null');
      navigate('/');
    } catch (err) {
      console.error('❌ Login error:', err);
      setError('Login failed. Check credentials or backend connection.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4">
      <Card className="w-full max-w-md" title="PeakBridge" subtitle="EV Peak Shaving Platform">
        <form onSubmit={handleSubmit} className="space-y-4">
          {isMockMode() && (
            <p className="rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
              Mock mode — any password works
            </p>
          )}
          {error && (
            <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>
          )}
          <div>
            <label className="mb-1 block text-xs text-muted">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-panel-border bg-surface px-3 py-2 text-sm text-white outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-panel-border bg-surface px-3 py-2 text-sm text-white outline-none focus:border-blue-500"
            />
          </div>
          <Button type="submit" loading={loading} className="w-full">
            Sign In
          </Button>
        </form>
      </Card>
    </div>
  );
}
