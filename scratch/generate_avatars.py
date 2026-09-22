import os

AVATAR_DIR = '/Users/thanh/Projects/pyweb/quiz/static/quiz/avatars'
os.makedirs(AVATAR_DIR, exist_ok=True)

# 16 Diverse SVG avatars
avatars = {
    'avatar-1': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg1" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#3b82f6"/>
      <stop offset="100%" stop-color="#1d4ed8"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg1)"/>
  <path d="M25 120 C25 90, 45 80, 60 80 C75 80, 95 90, 95 120 Z" fill="#1e293b"/>
  <path d="M48 80 L60 100 L72 80 Z" fill="#f8fafc"/>
  <path d="M57 85 L63 85 L61 105 L59 105 Z" fill="#ef4444"/>
  <circle cx="60" cy="54" r="25" fill="#fed7aa"/>
  <path d="M36 50 C36 30, 84 30, 84 50 C76 38, 44 38, 36 50 Z" fill="#451a03"/>
  <rect x="42" y="48" width="14" height="10" rx="3" fill="none" stroke="#0f172a" stroke-width="2.5"/>
  <rect x="64" y="48" width="14" height="10" rx="3" fill="none" stroke="#0f172a" stroke-width="2.5"/>
  <line x1="56" y1="53" x2="64" y2="53" stroke="#0f172a" stroke-width="2.5"/>
  <circle cx="49" cy="53" r="2" fill="#0f172a"/>
  <circle cx="71" cy="53" r="2" fill="#0f172a"/>
  <path d="M53 65 Q60 71 67 65" stroke="#9a3412" stroke-width="2" fill="none" stroke-linecap="round"/>
  <polygon points="60,18 100,32 60,42 20,32" fill="#09090b"/>
  <circle cx="60" cy="30" r="3" fill="#fbbf24"/>
  <path d="M60 30 Q75 32 78 48" stroke="#fbbf24" stroke-width="2.5" fill="none"/>
  <rect x="76" y="48" width="4" height="7" rx="1" fill="#f59e0b"/>
</svg>''',

    'avatar-2': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg2" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ec4899"/>
      <stop offset="100%" stop-color="#be185d"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg2)"/>
  <path d="M30 60 C26 75, 26 95, 36 108 L45 80 Z" fill="#78350f"/>
  <path d="M90 60 C94 75, 94 95, 84 108 L75 80 Z" fill="#78350f"/>
  <path d="M25 120 C25 90, 45 80, 60 80 C75 80, 95 90, 95 120 Z" fill="#0f172a"/>
  <path d="M50 80 L60 98 L70 80 Z" fill="#fdf2f8"/>
  <circle cx="60" cy="55" r="24" fill="#ffedd5"/>
  <path d="M36 50 C36 28, 84 28, 84 50 C80 38, 40 38, 36 50 Z" fill="#78350f"/>
  <circle cx="49" cy="53" r="2.5" fill="#1e293b"/>
  <circle cx="71" cy="53" r="2.5" fill="#1e293b"/>
  <path d="M45 48 Q49 46 53 48" stroke="#78350f" stroke-width="1.8" fill="none"/>
  <path d="M67 48 Q71 46 75 48" stroke="#78350f" stroke-width="1.8" fill="none"/>
  <circle cx="44" cy="59" r="4" fill="#f43f5e" opacity="0.4"/>
  <circle cx="76" cy="59" r="4" fill="#f43f5e" opacity="0.4"/>
  <path d="M54 64 Q60 70 66 64" stroke="#e11d48" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <polygon points="60,20 98,33 60,43 22,33" fill="#1e1b4b"/>
  <circle cx="60" cy="31" r="3" fill="#fbbf24"/>
  <path d="M60 31 Q76 33 80 48" stroke="#fbbf24" stroke-width="2.5" fill="none"/>
  <rect x="78" y="48" width="4" height="7" rx="1" fill="#f59e0b"/>
</svg>''',

    'avatar-3': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg3" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#06b6d4"/>
      <stop offset="100%" stop-color="#0891b2"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg3)"/>
  <!-- Crazy white hair -->
  <circle cx="32" cy="45" r="16" fill="#f1f5f9"/>
  <circle cx="88" cy="45" r="16" fill="#f1f5f9"/>
  <circle cx="45" cy="30" r="18" fill="#f1f5f9"/>
  <circle cx="75" cy="30" r="18" fill="#f1f5f9"/>
  <circle cx="60" cy="26" r="18" fill="#f1f5f9"/>
  <!-- Lab coat -->
  <path d="M25 120 C25 90, 45 80, 60 80 C75 80, 95 90, 95 120 Z" fill="#f8fafc"/>
  <path d="M50 80 L60 98 L70 80 Z" fill="#0284c7"/>
  <circle cx="60" cy="56" r="24" fill="#fed7aa"/>
  <!-- Goggles/glasses -->
  <circle cx="48" cy="52" r="10" fill="#e0f2fe" stroke="#0369a1" stroke-width="3"/>
  <circle cx="72" cy="52" r="10" fill="#e0f2fe" stroke="#0369a1" stroke-width="3"/>
  <line x1="58" y1="52" x2="62" y2="52" stroke="#0369a1" stroke-width="3"/>
  <circle cx="48" cy="52" r="3" fill="#0f172a"/>
  <circle cx="72" cy="52" r="3" fill="#0f172a"/>
  <!-- Mustache -->
  <path d="M48 66 Q60 62 72 66 Q60 73 48 66 Z" fill="#e2e8f0"/>
  <path d="M54 72 Q60 76 66 72" stroke="#9a3412" stroke-width="2" fill="none" stroke-linecap="round"/>
</svg>''',

    'avatar-4': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg4" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#6366f1"/>
      <stop offset="100%" stop-color="#4338ca"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg4)"/>
  <!-- Hoodie -->
  <path d="M25 120 C25 90, 45 78, 60 78 C75 78, 95 90, 95 120 Z" fill="#1e1b4b"/>
  <circle cx="60" cy="54" r="24" fill="#ffedd5"/>
  <!-- Trendy hair -->
  <path d="M36 48 C36 26, 84 26, 84 48 C76 34, 48 32, 36 48 Z" fill="#0f172a"/>
  <rect x="42" y="48" width="14" height="10" rx="2" fill="#0284c7" opacity="0.3" stroke="#38bdf8" stroke-width="2"/>
  <rect x="64" y="48" width="14" height="10" rx="2" fill="#0284c7" opacity="0.3" stroke="#38bdf8" stroke-width="2"/>
  <line x1="56" y1="53" x2="64" y2="53" stroke="#38bdf8" stroke-width="2"/>
  <circle cx="49" cy="53" r="2" fill="#f8fafc"/>
  <circle cx="71" cy="53" r="2" fill="#f8fafc"/>
  <path d="M54 66 Q60 70 66 66" stroke="#9a3412" stroke-width="2" fill="none" stroke-linecap="round"/>
  <!-- Headphone -->
  <path d="M34 54 C34 30, 86 30, 86 54" fill="none" stroke="#f59e0b" stroke-width="5" stroke-linecap="round"/>
  <rect x="30" y="48" width="8" height="16" rx="4" fill="#fbbf24"/>
  <rect x="82" y="48" width="8" height="16" rx="4" fill="#fbbf24"/>
</svg>''',

    'avatar-5': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg5" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#8b5cf6"/>
      <stop offset="100%" stop-color="#6d28d9"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg5)"/>
  <!-- Purple hair background -->
  <circle cx="40" cy="65" r="16" fill="#4c1d95"/>
  <circle cx="80" cy="65" r="16" fill="#4c1d95"/>
  <!-- Jacket -->
  <path d="M25 120 C25 90, 45 80, 60 80 C75 80, 95 90, 95 120 Z" fill="#0f172a"/>
  <circle cx="60" cy="55" r="24" fill="#fde68a"/>
  <!-- Hair top -->
  <path d="M35 50 C35 28, 85 28, 85 50 C80 36, 40 36, 35 50 Z" fill="#581c87"/>
  <!-- Big eyes -->
  <ellipse cx="48" cy="52" rx="4" ry="5" fill="#1e1b4b"/>
  <ellipse cx="72" cy="52" rx="4" ry="5" fill="#1e1b4b"/>
  <circle cx="47" cy="50" r="1.5" fill="#ffffff"/>
  <circle cx="71" cy="50" r="1.5" fill="#ffffff"/>
  <!-- Blush -->
  <circle cx="42" cy="60" r="4" fill="#f43f5e" opacity="0.4"/>
  <circle cx="78" cy="60" r="4" fill="#f43f5e" opacity="0.4"/>
  <path d="M54 64 Q60 69 66 64" stroke="#be123c" stroke-width="2.2" fill="none" stroke-linecap="round"/>
  <!-- Headphone -->
  <path d="M33 52 C33 26, 87 26, 87 52" fill="none" stroke="#06b6d4" stroke-width="4.5" stroke-linecap="round"/>
  <rect x="29" y="47" width="8" height="15" rx="4" fill="#22d3ee"/>
  <rect x="83" y="47" width="8" height="15" rx="4" fill="#22d3ee"/>
</svg>''',

    'avatar-6': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg6" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#10b981"/>
      <stop offset="100%" stop-color="#047857"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg6)"/>
  <!-- Robe -->
  <path d="M25 120 C25 90, 45 80, 60 80 C75 80, 95 90, 95 120 Z" fill="#064e3b"/>
  <circle cx="60" cy="56" r="24" fill="#fed7aa"/>
  <!-- Long beard -->
  <path d="M42 66 C42 90, 78 90, 78 66 Z" fill="#f1f5f9"/>
  <!-- Eyes & Eyebrows -->
  <circle cx="49" cy="52" r="2.5" fill="#0f172a"/>
  <circle cx="71" cy="52" r="2.5" fill="#0f172a"/>
  <path d="M44 46 Q49 43 54 46" stroke="#e2e8f0" stroke-width="3" fill="none"/>
  <path d="M66 46 Q71 43 76 46" stroke="#e2e8f0" stroke-width="3" fill="none"/>
  <path d="M55 70 Q60 74 65 70" stroke="#047857" stroke-width="2" fill="none"/>
  <!-- Wizard Hat -->
  <polygon points="60,8 86,40 34,40" fill="#064e3b"/>
  <ellipse cx="60" cy="40" rx="30" ry="7" fill="#047857"/>
  <text x="60" y="32" font-size="12" fill="#fbbf24" text-anchor="middle" font-weight="bold">∑</text>
</svg>''',

    'avatar-7': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg7" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1e1b4b"/>
    </linearGradient>
    <linearGradient id="visor" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f59e0b"/>
      <stop offset="100%" stop-color="#d97706"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg7)"/>
  <!-- Stars -->
  <circle cx="25" cy="25" r="1.5" fill="#ffffff" opacity="0.8"/>
  <circle cx="95" cy="30" r="1.5" fill="#ffffff" opacity="0.8"/>
  <circle cx="85" cy="90" r="1" fill="#ffffff" opacity="0.6"/>
  <!-- Spacesuit body -->
  <path d="M25 120 C25 85, 45 78, 60 78 C75 78, 95 85, 95 120 Z" fill="#e2e8f0"/>
  <rect x="52" y="90" width="16" height="14" rx="3" fill="#0284c7"/>
  <!-- Helmet -->
  <circle cx="60" cy="50" r="30" fill="#f8fafc" stroke="#cbd5e1" stroke-width="3"/>
  <!-- Visor -->
  <rect x="40" y="38" width="40" height="24" rx="12" fill="url(#visor)"/>
  <path d="M45 42 Q60 38 75 42" stroke="#fef08a" stroke-width="2" fill="none" opacity="0.7"/>
</svg>''',

    'avatar-8': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg8" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f97316"/>
      <stop offset="100%" stop-color="#ea580c"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg8)"/>
  <!-- T-shirt -->
  <path d="M25 120 C25 90, 45 80, 60 80 C75 80, 95 90, 95 120 Z" fill="#0284c7"/>
  <circle cx="60" cy="55" r="24" fill="#ffedd5"/>
  <circle cx="49" cy="54" r="2.5" fill="#0f172a"/>
  <circle cx="71" cy="54" r="2.5" fill="#0f172a"/>
  <path d="M53 65 Q60 72 67 65" stroke="#9a3412" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <!-- Backward cap -->
  <path d="M35 50 C35 30, 85 30, 85 50 Z" fill="#e11d48"/>
  <ellipse cx="60" cy="50" rx="26" ry="6" fill="#be123c"/>
  <path d="M70 48 Q85 46 92 50 Q85 55 70 52 Z" fill="#9f1239"/>
</svg>''',

    'avatar-9': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg9" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#14b8a6"/>
      <stop offset="100%" stop-color="#0f766e"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg9)"/>
  <!-- Hair back -->
  <circle cx="38" cy="62" r="16" fill="#18181b"/>
  <circle cx="82" cy="62" r="16" fill="#18181b"/>
  <!-- Striped shirt -->
  <path d="M25 120 C25 90, 45 80, 60 80 C75 80, 95 90, 95 120 Z" fill="#f8fafc"/>
  <line x1="30" y1="95" x2="90" y2="95" stroke="#0f172a" stroke-width="3"/>
  <line x1="26" y1="108" x2="94" y2="108" stroke="#0f172a" stroke-width="3"/>
  <circle cx="60" cy="56" r="24" fill="#fed7aa"/>
  <circle cx="48" cy="54" r="2.5" fill="#0f172a"/>
  <circle cx="72" cy="54" r="2.5" fill="#0f172a"/>
  <path d="M54 65 Q60 70 66 65" stroke="#be123c" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <!-- Beret -->
  <ellipse cx="60" cy="38" rx="28" ry="12" fill="#dc2626"/>
  <circle cx="60" cy="26" r="2" fill="#991b1b"/>
</svg>''',

    'avatar-10': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg10" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#fb923c"/>
      <stop offset="100%" stop-color="#c2410c"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg10)"/>
  <!-- Cat Ears -->
  <polygon points="34,46 44,18 60,38" fill="#ea580c"/>
  <polygon points="38,44 45,24 56,38" fill="#fed7aa"/>
  <polygon points="86,46 76,18 60,38" fill="#ea580c"/>
  <polygon points="82,44 75,24 64,38" fill="#fed7aa"/>
  <!-- Body -->
  <path d="M28 120 C28 92, 45 82, 60 82 C75 82, 92 92, 92 120 Z" fill="#fed7aa"/>
  <!-- Face -->
  <circle cx="60" cy="60" r="28" fill="#f97316"/>
  <!-- Glasses -->
  <rect x="40" y="52" width="16" height="12" rx="3" fill="none" stroke="#0f172a" stroke-width="2.5"/>
  <rect x="64" y="52" width="16" height="12" rx="3" fill="none" stroke="#0f172a" stroke-width="2.5"/>
  <line x1="56" y1="58" x2="64" y2="58" stroke="#0f172a" stroke-width="2.5"/>
  <circle cx="48" cy="58" r="2.5" fill="#0f172a"/>
  <circle cx="72" cy="58" r="2.5" fill="#0f172a"/>
  <!-- Nose & Mouth -->
  <polygon points="60,67 56,64 64,64" fill="#be123c"/>
  <path d="M56 69 Q60 73 64 69" stroke="#7c2d12" stroke-width="1.8" fill="none"/>
  <!-- Whiskers -->
  <line x1="32" y1="64" x2="42" y2="66" stroke="#7c2d12" stroke-width="1.5"/>
  <line x1="32" y1="70" x2="42" y2="70" stroke="#7c2d12" stroke-width="1.5"/>
  <line x1="78" y1="66" x2="88" y2="64" stroke="#7c2d12" stroke-width="1.5"/>
  <line x1="78" y1="70" x2="88" y2="70" stroke="#7c2d12" stroke-width="1.5"/>
</svg>''',

    'avatar-11': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg11" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#3b82f6"/>
      <stop offset="100%" stop-color="#1e3a8a"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg11)"/>
  <!-- Owl Body -->
  <ellipse cx="60" cy="65" rx="32" ry="36" fill="#78350f"/>
  <ellipse cx="60" cy="72" rx="20" ry="22" fill="#fef3c7"/>
  <!-- Owl Ears -->
  <polygon points="34,40 44,22 52,38" fill="#78350f"/>
  <polygon points="86,40 76,22 68,38" fill="#78350f"/>
  <!-- Huge Eyes -->
  <circle cx="46" cy="50" r="14" fill="#ffffff"/>
  <circle cx="74" cy="50" r="14" fill="#ffffff"/>
  <circle cx="46" cy="50" r="8" fill="#fbbf24"/>
  <circle cx="74" cy="50" r="8" fill="#fbbf24"/>
  <circle cx="46" cy="50" r="4" fill="#0f172a"/>
  <circle cx="74" cy="50" r="4" fill="#0f172a"/>
  <!-- Beak -->
  <polygon points="60,56 54,64 66,64" fill="#f59e0b"/>
  <!-- Small Grad Cap -->
  <polygon points="60,18 78,25 60,30 42,25" fill="#0f172a"/>
  <circle cx="60" cy="24" r="1.5" fill="#fbbf24"/>
</svg>''',

    'avatar-12': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg12" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f59e0b"/>
      <stop offset="100%" stop-color="#b45309"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg12)"/>
  <!-- Fox Ears -->
  <polygon points="32,45 42,16 58,38" fill="#ea580c"/>
  <polygon points="36,42 43,22 54,36" fill="#ffffff"/>
  <polygon points="88,45 78,16 62,38" fill="#ea580c"/>
  <polygon points="84,42 77,22 66,36" fill="#ffffff"/>
  <!-- Head & Cheeks -->
  <circle cx="60" cy="60" r="28" fill="#ea580c"/>
  <path d="M34 60 C34 76, 52 82, 60 72 C68 82, 86 76, 86 60 Z" fill="#ffffff"/>
  <!-- Eyes -->
  <ellipse cx="48" cy="54" rx="3" ry="2" fill="#0f172a"/>
  <ellipse cx="72" cy="54" rx="3" ry="2" fill="#0f172a"/>
  <!-- Nose -->
  <circle cx="60" cy="68" r="3" fill="#0f172a"/>
  <path d="M56 73 Q60 76 64 73" stroke="#0f172a" stroke-width="1.5" fill="none"/>
</svg>''',

    'avatar-13': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg13" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0284c7"/>
      <stop offset="100%" stop-color="#0369a1"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg13)"/>
  <!-- Antenna -->
  <line x1="60" y1="24" x2="60" y2="35" stroke="#38bdf8" stroke-width="3"/>
  <circle cx="60" cy="22" r="4" fill="#fbbf24"/>
  <!-- Robot Head -->
  <rect x="34" y="35" width="52" height="42" rx="12" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="3"/>
  <!-- Screen/Eyes area -->
  <rect x="42" y="44" width="36" height="18" rx="6" fill="#0f172a"/>
  <circle cx="51" cy="53" r="3.5" fill="#38bdf8"/>
  <circle cx="69" cy="53" r="3.5" fill="#38bdf8"/>
  <!-- Smile -->
  <path d="M52 68 Q60 74 68 68" stroke="#0284c7" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <!-- Body -->
  <rect x="40" y="85" width="40" height="35" rx="8" fill="#e2e8f0"/>
  <circle cx="60" cy="98" r="5" fill="#22c55e"/>
</svg>''',

    'avatar-14': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg14" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#475569"/>
      <stop offset="100%" stop-color="#1e293b"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg14)"/>
  <!-- Suit -->
  <path d="M25 120 C25 90, 45 80, 60 80 C75 80, 95 90, 95 120 Z" fill="#0f172a"/>
  <path d="M48 80 L60 100 L72 80 Z" fill="#ffffff"/>
  <polygon points="60,86 64,88 62,106 58,106 56,88" fill="#0284c7"/>
  <!-- Face -->
  <circle cx="60" cy="54" r="24" fill="#fed7aa"/>
  <!-- Hair & Gray temples -->
  <path d="M36 50 C36 28, 84 28, 84 50 C78 36, 42 36, 36 50 Z" fill="#334155"/>
  <path d="M35 48 C35 40, 40 38, 44 42" stroke="#94a3b8" stroke-width="2" fill="none"/>
  <path d="M85 48 C85 40, 80 38, 76 42" stroke="#94a3b8" stroke-width="2" fill="none"/>
  <!-- Glasses -->
  <circle cx="48" cy="52" r="7" fill="none" stroke="#64748b" stroke-width="2"/>
  <circle cx="72" cy="52" r="7" fill="none" stroke="#64748b" stroke-width="2"/>
  <line x1="55" y1="52" x2="65" y2="52" stroke="#64748b" stroke-width="2"/>
  <circle cx="48" cy="52" r="2" fill="#0f172a"/>
  <circle cx="72" cy="52" r="2" fill="#0f172a"/>
  <path d="M53 66 Q60 70 67 66" stroke="#9a3412" stroke-width="2" fill="none" stroke-linecap="round"/>
</svg>''',

    'avatar-15': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg15" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0d9488"/>
      <stop offset="100%" stop-color="#115e59"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg15)"/>
  <!-- Hair Bun -->
  <circle cx="60" cy="26" r="12" fill="#451a03"/>
  <!-- Dress / Shirt -->
  <path d="M25 120 C25 90, 45 80, 60 80 C75 80, 95 90, 95 120 Z" fill="#134e4a"/>
  <path d="M48 80 L60 96 L72 80 Z" fill="#ccfbf1"/>
  <!-- Face -->
  <circle cx="60" cy="55" r="24" fill="#ffedd5"/>
  <!-- Hair front -->
  <path d="M36 50 C36 30, 84 30, 84 50 C76 38, 44 38, 36 50 Z" fill="#451a03"/>
  <!-- Glasses -->
  <rect x="42" y="50" width="13" height="9" rx="2.5" fill="none" stroke="#b45309" stroke-width="2"/>
  <rect x="65" y="50" width="13" height="9" rx="2.5" fill="none" stroke="#b45309" stroke-width="2"/>
  <line x1="55" y1="54" x2="65" y2="54" stroke="#b45309" stroke-width="2"/>
  <circle cx="48.5" cy="54.5" r="2" fill="#0f172a"/>
  <circle cx="71.5" cy="54.5" r="2" fill="#0f172a"/>
  <circle cx="43" cy="62" r="3" fill="#f43f5e" opacity="0.4"/>
  <circle cx="77" cy="62" r="3" fill="#f43f5e" opacity="0.4"/>
  <path d="M54 66 Q60 70 66 66" stroke="#be123c" stroke-width="2.2" fill="none" stroke-linecap="round"/>
</svg>''',

    'avatar-16': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%">
  <defs>
    <linearGradient id="bg16" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#eab308"/>
      <stop offset="100%" stop-color="#ca8a04"/>
    </linearGradient>
  </defs>
  <rect width="120" height="120" rx="60" fill="url(#bg16)"/>
  <!-- Laurel wreath -->
  <circle cx="34" cy="52" r="6" fill="#15803d" opacity="0.9"/>
  <circle cx="38" cy="40" r="6" fill="#15803d" opacity="0.9"/>
  <circle cx="46" cy="30" r="6" fill="#15803d" opacity="0.9"/>
  <circle cx="86" cy="52" r="6" fill="#15803d" opacity="0.9"/>
  <circle cx="82" cy="40" r="6" fill="#15803d" opacity="0.9"/>
  <circle cx="74" cy="30" r="6" fill="#15803d" opacity="0.9"/>
  <!-- Gold Medal & Ribbon -->
  <path d="M25 120 C25 90, 45 80, 60 80 C75 80, 95 90, 95 120 Z" fill="#1e1b4b"/>
  <polygon points="52,80 60,98 68,80" fill="#dc2626"/>
  <circle cx="60" cy="102" r="8" fill="#fbbf24" stroke="#f59e0b" stroke-width="2"/>
  <text x="60" y="105" font-size="8" fill="#78350f" text-anchor="middle" font-weight="bold">1</text>
  <!-- Face -->
  <circle cx="60" cy="54" r="23" fill="#fed7aa"/>
  <circle cx="49" cy="52" r="2.5" fill="#0f172a"/>
  <circle cx="71" cy="52" r="2.5" fill="#0f172a"/>
  <!-- Crown / Star -->
  <polygon points="60,20 63,27 70,27 65,31 67,38 60,34 53,38 55,31 50,27 57,27" fill="#fbbf24"/>
  <path d="M53 64 Q60 70 67 64" stroke="#9a3412" stroke-width="2.5" fill="none" stroke-linecap="round"/>
</svg>'''
}

for name, svg_content in avatars.items():
    path = os.path.join(AVATAR_DIR, f"{name}.svg")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(svg_content)

print(f"Successfully generated {len(avatars)} SVG avatars in {AVATAR_DIR}")
