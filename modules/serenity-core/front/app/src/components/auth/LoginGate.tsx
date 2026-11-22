import React, { useState } from 'react';
import { Shield, Lock, LogIn, Globe, AlertCircle, Loader2, KeyRound } from 'lucide-react';
import { useDemo } from '../../context/DemoContext';

export const LoginGate: React.FC = () => {
  const { authStatus, authConfig, authError, loginWithOidc, language, setLanguage, t } = useDemo();
  const [signingIn, setSigningIn] = useState(false);

  const handleSignIn = async () => {
    setSigningIn(true);
    try {
      await loginWithOidc();
    } catch {
      setSigningIn(false);
    }
  };

  const providerLabel =
    authConfig?.mode === 'cognito' ? 'AWS Cognito' : t('SSO OIDC', 'OIDC SSO');

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center">
              <Shield className="w-5 h-5 text-sky-400" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-white tracking-tight">Serenity-Ops</h1>
              <p className="text-[11px] text-slate-400">CloudSecOps &amp; AIOps Console</p>
            </div>
          </div>

          <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5 text-xs font-medium">
            <Globe className="w-3.5 h-3.5 text-slate-400 ml-2 mr-1" />
            <button
              onClick={() => setLanguage('fr')}
              className={`px-2 py-1 rounded-md transition-colors ${
                language === 'fr' ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              FR
            </button>
            <button
              onClick={() => setLanguage('en')}
              className={`px-2 py-1 rounded-md transition-colors ${
                language === 'en' ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              EN
            </button>
          </div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-7 shadow-2xl">
          {authStatus === 'checking' ? (
            <div className="py-10 flex flex-col items-center justify-center text-center gap-3">
              <Loader2 className="w-7 h-7 text-sky-400 animate-spin" />
              <p className="text-sm font-medium text-slate-200">
                {t('Vérification de la session...', 'Verifying session...')}
              </p>
              <p className="text-xs text-slate-400">
                {t(
                  'Validation OIDC / PKCE auprès de votre environnement AWS.',
                  'Validating OIDC / PKCE with your AWS environment.'
                )}
              </p>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 text-xs font-medium text-emerald-400 mb-3">
                <Lock className="w-3.5 h-3.5" />
                <span>{t('Accès opérateur authentifié requis', 'Authenticated operator access required')}</span>
              </div>

              <h2 className="text-xl font-semibold text-white tracking-tight mb-2">
                {t('Connexion à la console live', 'Sign in to the live console')}
              </h2>
              <p className="text-xs text-slate-400 leading-relaxed mb-6">
                {t(
                  'Toutes les routes API (/api/state, /api/chat et les approbations Human-in-the-Loop) exigent un jeton JWT signé vérifié côté Lambda.',
                  'All API routes (/api/state, /api/chat, and Human-in-the-Loop approvals) require a signed JWT verified server-side by Lambda.'
                )}
              </p>

              {authError && (
                <div className="mb-5 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 flex items-start gap-2.5 text-xs text-rose-300">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-400" />
                  <span>{authError}</span>
                </div>
              )}

              <button
                onClick={handleSignIn}
                disabled={signingIn}
                className="w-full flex items-center justify-center gap-2.5 px-4 py-2.5 rounded-lg bg-sky-500 hover:bg-sky-400 disabled:opacity-60 text-slate-950 font-semibold text-sm transition-colors shadow-sm"
              >
                {signingIn ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <LogIn className="w-4 h-4" />
                )}
                <span>
                  {t(`Se connecter avec ${providerLabel}`, `Sign in with ${providerLabel}`)}
                </span>
              </button>

              <div className="mt-6 pt-5 border-t border-slate-800 space-y-2 text-[11px] text-slate-400">
                <div className="flex items-center gap-2">
                  <KeyRound className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                  <span>
                    {t(
                      'OAuth 2.0 Authorization Code + PKCE (aucun secret stocké dans le navigateur)',
                      'OAuth 2.0 Authorization Code + PKCE (no client secret stored in browser)'
                    )}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Shield className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                  <span>
                    {t(
                      'Votre identité est journalisée dans DynamoDB Hub et AWS CloudTrail (STS RoleSessionName)',
                      'Your identity is audited in DynamoDB Hub and AWS CloudTrail (STS RoleSessionName)'
                    )}
                  </span>
                </div>
              </div>
            </>
          )}
        </div>

        <p className="mt-6 text-center text-[11px] text-slate-500">
          Crafted by <span className="text-slate-400 font-medium">e-serenity</span>
        </p>
      </div>
    </div>
  );
};
