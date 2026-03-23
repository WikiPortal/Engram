"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { login, register, isLoggedIn } from "@/lib/auth";

type Mode = "signin" | "signup";

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode]     = useState<Mode>("signin");
  const [email, setEmail]   = useState("");
  const [username, setUser] = useState("");
  const [password, setPass] = useState("");
  const [error, setError]   = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => { if (isLoggedIn()) router.replace("/"); }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError(""); setLoading(true);
    try {
      if (mode === "signin") { await login(email, password); }
      else {
        if (username.length < 3) { setError("Username must be at least 3 characters"); setLoading(false); return; }
        if (password.length < 8) { setError("Password must be at least 8 characters"); setLoading(false); return; }
        await register(email, username, password);
      }
      router.replace("/");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally { setLoading(false); }
  }

  return (
    <div style={{minHeight:"100vh",background:"var(--bg)",display:"flex",alignItems:"center",justifyContent:"center",padding:16,fontFamily:"'Geist',sans-serif"}}>
      <div style={{width:"100%",maxWidth:380}}>

        {/* Logo */}
        <div style={{textAlign:"center",marginBottom:32}}>
          <div style={{display:"flex",alignItems:"center",justifyContent:"center",gap:10,marginBottom:8}}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round">
              <path d="M12 2a5 5 0 0 1 5 5v1a5 5 0 0 1-5 5 5 5 0 0 1-5-5V7a5 5 0 0 1 5-5z"/><path d="M2 18a10 10 0 0 1 20 0"/>
            </svg>
            <span style={{fontSize:22,fontWeight:700,letterSpacing:"-0.5px",color:"var(--text)"}}>Engram</span>
          </div>
          <p style={{fontSize:13,color:"var(--text-3)"}}>Your private AI memory layer</p>
        </div>

        {/* Card */}
        <div style={{background:"var(--bg-2)",border:"1px solid var(--border)",borderRadius:20,padding:24}}>

          {/* Mode tabs */}
          <div style={{display:"flex",gap:4,background:"var(--bg-3)",borderRadius:12,padding:4,marginBottom:24}}>
            {(["signin","signup"] as Mode[]).map(m=>(
              <button key={m} onClick={()=>{setMode(m);setError("");}} style={{
                flex:1,padding:"8px 0",fontSize:13,fontWeight:500,borderRadius:9,border:"none",cursor:"pointer",
                background:mode===m?"var(--bg-4)":"transparent",
                color:mode===m?"var(--text)":"var(--text-3)",
                boxShadow:mode===m?"0 1px 3px rgba(0,0,0,0.3)":"none",
                transition:"all 0.15s"
              }}>{m==="signin"?"Sign in":"Sign up"}</button>
            ))}
          </div>

          <form onSubmit={submit} style={{display:"flex",flexDirection:"column",gap:14}}>
            {/* Email */}
            <div>
              <label style={{display:"block",fontSize:11,color:"var(--text-3)",textTransform:"uppercase",letterSpacing:"0.5px",marginBottom:6,fontWeight:500}}>Email</label>
              <input type="email" value={email} onChange={e=>setEmail(e.target.value)} required placeholder="you@example.com" style={{
                width:"100%",background:"var(--bg-3)",border:"1px solid var(--border)",borderRadius:12,
                padding:"10px 14px",fontSize:13,color:"var(--text)",outline:"none",boxSizing:"border-box",
                fontFamily:"inherit",transition:"border-color 0.15s"
              }} onFocus={e=>(e.target.style.borderColor="var(--border-2)")} onBlur={e=>(e.target.style.borderColor="var(--border)")}/>
            </div>

            {/* Username */}
            {mode==="signup"&&(
              <div>
                <label style={{display:"block",fontSize:11,color:"var(--text-3)",textTransform:"uppercase",letterSpacing:"0.5px",marginBottom:6,fontWeight:500}}>Username</label>
                <input type="text" value={username} onChange={e=>setUser(e.target.value)} required placeholder="yourname" minLength={3} maxLength={50} style={{
                  width:"100%",background:"var(--bg-3)",border:"1px solid var(--border)",borderRadius:12,
                  padding:"10px 14px",fontSize:13,color:"var(--text)",outline:"none",boxSizing:"border-box",
                  fontFamily:"inherit",transition:"border-color 0.15s"
                }} onFocus={e=>(e.target.style.borderColor="var(--border-2)")} onBlur={e=>(e.target.style.borderColor="var(--border)")}/>
              </div>
            )}

            {/* Password */}
            <div>
              <label style={{display:"block",fontSize:11,color:"var(--text-3)",textTransform:"uppercase",letterSpacing:"0.5px",marginBottom:6,fontWeight:500}}>Password</label>
              <input type="password" value={password} onChange={e=>setPass(e.target.value)} required
                placeholder={mode==="signup"?"Min 8 characters":"••••••••"} minLength={mode==="signup"?8:1} style={{
                  width:"100%",background:"var(--bg-3)",border:"1px solid var(--border)",borderRadius:12,
                  padding:"10px 14px",fontSize:13,color:"var(--text)",outline:"none",boxSizing:"border-box",
                  fontFamily:"inherit",transition:"border-color 0.15s"
                }} onFocus={e=>(e.target.style.borderColor="var(--border-2)")} onBlur={e=>(e.target.style.borderColor="var(--border)")}/>
            </div>

            {/* Error */}
            {error&&(
              <div style={{display:"flex",alignItems:"flex-start",gap:8,background:"rgba(239,68,68,0.08)",border:"1px solid rgba(239,68,68,0.2)",borderRadius:10,padding:"10px 12px"}}>
                <span style={{color:"var(--red)",fontSize:13,flexShrink:0}}>⚠</span>
                <p style={{fontSize:12,color:"#fca5a5",lineHeight:1.5}}>{error}</p>
              </div>
            )}

            {/* Submit */}
            <button type="submit" disabled={loading} style={{
              padding:"11px 0",background:"var(--accent)",border:"none",borderRadius:12,
              color:"white",fontSize:13,fontWeight:500,cursor:loading?"default":"pointer",
              opacity:loading?0.6:1,transition:"all 0.15s",marginTop:4,fontFamily:"inherit"
            }}
              onMouseEnter={e=>{if(!loading)(e.currentTarget as HTMLElement).style.background="var(--accent-2)";}}
              onMouseLeave={e=>{(e.currentTarget as HTMLElement).style.background="var(--accent)";}}>
              {loading?(mode==="signin"?"Signing in…":"Creating account…"):(mode==="signin"?"Sign in →":"Create account →")}
            </button>
          </form>

          <p style={{textAlign:"center",fontSize:12,color:"var(--text-3)",marginTop:18}}>
            {mode==="signin"?"No account? ":"Already have an account? "}
            <button onClick={()=>{setMode(mode==="signin"?"signup":"signin");setError("");}} style={{
              color:"var(--accent-2)",background:"none",border:"none",cursor:"pointer",fontSize:12,
              textDecoration:"underline",textUnderlineOffset:3
            }}>{mode==="signin"?"Sign up":"Sign in"}</button>
          </p>
        </div>

        <p style={{textAlign:"center",fontSize:11,color:"var(--text-3)",marginTop:20,lineHeight:1.6}}>
          Private & self-hosted · Your data stays with you
        </p>
      </div>
    </div>
  );
}
