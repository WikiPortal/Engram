"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { api, Memory, friendlyError, EngramApiError } from "@/lib/api";
import { getUser, logout, isLoggedIn, type User } from "@/lib/auth";

type Role = "user" | "assistant";
interface Message { id: string; role: Role; content: string; memoriesUsed?: number; isThinking?: boolean; isError?: boolean; }
interface Conversation { id: string; title: string; messages: Message[]; createdAt: number; }
type Panel = "chat" | "memories";

const OB_QUESTIONS = [
  "What is your full name and what do you do professionally?",
  "What are your main technical skills or areas of expertise?",
  "What projects are you currently working on?",
  "What are your long-term goals — personal and professional?",
  "What do you like and dislike? (hobbies, foods, preferences)",
  "Who are the important people in your life?",
  "What tools, languages, or frameworks do you use daily?",
  "What topics are you actively learning right now?",
  "Any recurring commitments, routines, or constraints I should know?",
  "Anything else important you'd want me to always remember?",
];

function uid() { return Math.random().toString(36).slice(2, 9); }
function timeAgo(iso: string) {
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86400)}d ago`;
}
function renderMd(t: string) {
  return t
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/```[\w]*\n?([\s\S]*?)```/g,"<pre><code>$1</code></pre>")
    .replace(/`([^`]+)`/g,"<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g,"<strong>$1</strong>")
    .replace(/\*([^*\n]+)\*/g,"<em>$1</em>")
    .replace(/^### (.+)$/gm,"<h3>$1</h3>").replace(/^## (.+)$/gm,"<h2>$1</h2>").replace(/^# (.+)$/gm,"<h1>$1</h1>")
    .replace(/^[*-] (.+)$/gm,"<li>$1</li>")
    .replace(/\n\n+/g,"</p><p>").replace(/\n/g,"<br>");
}
function titleFrom(msg: string) { return msg.slice(0,42)+(msg.length>42?"…":""); }

function ThinkingDots() {
  return (
    <div className="flex items-center gap-1 py-1">
      {[0,1,2].map(i=>(
        <span key={i} className="w-1.5 h-1.5 rounded-full animate-pulse-dot"
          style={{background:"var(--accent)",animationDelay:`${i*0.18}s`,opacity:0.5}}/>
      ))}
    </div>
  );
}

export default function Home() {
  const [user, setUser]               = useState<User|null>(null);
  const [online, setOnline]           = useState<boolean|null>(null);
  const [panel, setPanel]             = useState<Panel>("chat");
  const [sidebarOpen, setSidebar]     = useState(true);
  const [showOb, setShowOb]           = useState(false);
  const [convs, setConvs]             = useState<Conversation[]>([]);
  const [activeId, setActiveId]       = useState("");
  const [input, setInput]             = useState("");
  const [sending, setSending]         = useState(false);
  const [memories, setMemories]       = useState<Memory[]>([]);
  const [memSearch, setMemSearch]     = useState("");
  const [loadingMem, setLoadingMem]   = useState(false);
  const [obStep, setObStep]           = useState(0);
  const [obAnswers, setObAnswers]     = useState<string[]>(Array(OB_QUESTIONS.length).fill(""));
  const [obSaving, setObSaving]       = useState(false);
  const [obDone, setObDone]           = useState(false);
  const messagesEnd                   = useRef<HTMLDivElement>(null);
  const inputRef                      = useRef<HTMLTextAreaElement>(null);

  const userId      = user?.user_id ?? "default";
  const activeConv  = convs.find(c=>c.id===activeId);
  const messages    = activeConv?.messages ?? [];

  useEffect(()=>{
    const u = getUser();
    if(!u||!isLoggedIn()){window.location.href="/auth";return;}
    setUser(u);
    try {
      const saved = localStorage.getItem(`engram_convs_${u.user_id}`);
      if(saved){const p:Conversation[]=JSON.parse(saved);setConvs(p);if(p.length>0)setActiveId(p[0].id);}
      else{const c:Conversation={id:uid(),title:"New conversation",messages:[],createdAt:Date.now()};setConvs([c]);setActiveId(c.id);}
    } catch{const c:Conversation={id:uid(),title:"New conversation",messages:[],createdAt:Date.now()};setConvs([c]);setActiveId(c.id);}
    api.health().then(()=>setOnline(true)).catch(()=>setOnline(false));
  },[]);

  useEffect(()=>{messagesEnd.current?.scrollIntoView({behavior:"smooth"});},[messages]);
  useEffect(()=>{if(!user||convs.length===0)return;localStorage.setItem(`engram_convs_${user.user_id}`,JSON.stringify(convs));},[convs,user]);
  useEffect(()=>{if(!inputRef.current)return;inputRef.current.style.height="auto";inputRef.current.style.height=Math.min(inputRef.current.scrollHeight,160)+"px";},[input]);

  function newConv(initial=false){
    const c:Conversation={id:uid(),title:"New conversation",messages:[],createdAt:Date.now()};
    setConvs(p=>[c,...p]);setActiveId(c.id);
    if(!initial)setTimeout(()=>inputRef.current?.focus(),50);
  }
  function delConv(id:string){
    setConvs(p=>{const n=p.filter(c=>c.id!==id);if(activeId===id)setActiveId(n[0]?.id??"");return n;});
  }
  function upd(id:string,fn:(c:Conversation)=>Conversation){setConvs(p=>p.map(c=>c.id===id?fn(c):c));}

  const sendMessage = useCallback(async()=>{
    const text=input.trim();if(!text||sending)return;
    let cid=activeId;
    if(!cid){const c:Conversation={id:uid(),title:titleFrom(text),messages:[],createdAt:Date.now()};setConvs(p=>[c,...p]);setActiveId(c.id);cid=c.id;}
    const uid1=uid(),uid2=uid();
    const userMsg:Message={id:uid1,role:"user",content:text};
    const thinkMsg:Message={id:uid2,role:"assistant",content:"",isThinking:true};
    upd(cid,c=>({...c,title:c.messages.length===0?titleFrom(text):c.title,messages:[...c.messages,userMsg,thinkMsg]}));
    setInput("");setSending(true);
    const hist=(convs.find(c=>c.id===cid)?.messages??[]).filter(m=>!m.isThinking).map(m=>({role:m.role,content:m.content}));
    try {
      const res=await api.chat(text,userId,hist);
      upd(cid,c=>({...c,messages:c.messages.map(m=>m.id===uid2?{...m,content:res.response,isThinking:false,memoriesUsed:res.memories_used}:m)}));
    } catch(e){
      upd(cid,c=>({...c,messages:c.messages.map(m=>m.id===uid2?{...m,content:friendlyError(e),isThinking:false,isError:true}:m)}));
    } finally{setSending(false);setTimeout(()=>inputRef.current?.focus(),50);}
  },[input,sending,activeId,convs,userId]);

  const handleKey=(e:React.KeyboardEvent)=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendMessage();}};

  const loadMems=useCallback(async()=>{
    setLoadingMem(true);
    try{setMemories(await api.list(userId,200));}catch{setMemories([]);}
    finally{setLoadingMem(false);}
  },[userId]);
  useEffect(()=>{if(panel==="memories")loadMems();},[panel,loadMems]);
  const filteredMems=memories.filter(m=>m.content.toLowerCase().includes(memSearch.toLowerCase()));

  const saveOb=async()=>{
    const ans=obAnswers[obStep].trim();if(!ans)return;
    setObSaving(true);
    try{await api.store(`${OB_QUESTIONS[obStep]}\n${ans}`,userId,["onboarding"]);}catch{}
    setObSaving(false);
    if(obStep<OB_QUESTIONS.length-1)setObStep(s=>s+1);else setObDone(true);
  };

  return (
    <div style={{display:"flex",height:"100vh",background:"var(--bg)",color:"var(--text)",overflow:"hidden",fontFamily:"'Geist',sans-serif"}}>

      {/* Sidebar */}
      <aside style={{
        width:sidebarOpen?260:0,flexShrink:0,overflow:"hidden",
        borderRight:sidebarOpen?"1px solid var(--border)":"none",
        display:"flex",flexDirection:"column",
        transition:"width 0.2s ease",background:"var(--bg)"
      }}>
        {/* Sidebar top */}
        <div style={{padding:"12px 16px",borderBottom:"1px solid var(--border)",display:"flex",alignItems:"center",justifyContent:"space-between",flexShrink:0}}>
          <div style={{display:"flex",alignItems:"center",gap:10}}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a5 5 0 0 1 5 5v1a5 5 0 0 1-5 5 5 5 0 0 1-5-5V7a5 5 0 0 1 5-5z"/><path d="M2 18a10 10 0 0 1 20 0"/>
            </svg>
            <span style={{fontSize:14,fontWeight:600,letterSpacing:"-0.3px"}}>Engram</span>
          </div>
          <button onClick={()=>newConv()} title="New chat" style={{width:28,height:28,borderRadius:8,border:"1px solid var(--border)",background:"transparent",cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center",color:"var(--text-2)"}}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 5v14M5 12h14"/></svg>
          </button>
        </div>

        {/* Panel tabs */}
        <div style={{display:"flex",gap:4,padding:"8px 12px",flexShrink:0}}>
          {(["chat","memories"] as Panel[]).map(p=>(
            <button key={p} onClick={()=>setPanel(p)} style={{
              flex:1,padding:"6px 0",fontSize:12,fontWeight:500,borderRadius:8,border:"none",cursor:"pointer",
              background:panel===p?"var(--bg-3)":"transparent",
              color:panel===p?"var(--text)":"var(--text-3)",transition:"all 0.15s"
            }}>{p==="chat"?"Chats":"Memories"}</button>
          ))}
        </div>

        {/* Panel content */}
        <div style={{flex:1,overflowY:"auto",padding:"0 8px 8px"}}>
          {panel==="chat"&&(
            <div style={{display:"flex",flexDirection:"column",gap:2}}>
              {convs.length===0&&<p style={{textAlign:"center",color:"var(--text-3)",fontSize:12,padding:"32px 0"}}>No conversations yet</p>}
              {convs.map(conv=>(
                <div key={conv.id} onClick={()=>setActiveId(conv.id)} style={{
                  display:"flex",alignItems:"center",justifyContent:"space-between",
                  padding:"10px 12px",borderRadius:10,cursor:"pointer",
                  background:activeId===conv.id?"var(--bg-3)":"transparent",
                  border:activeId===conv.id?"1px solid var(--border)":"1px solid transparent",
                  transition:"all 0.1s"
                }} className="group">
                  <div style={{minWidth:0,flex:1}}>
                    <p style={{fontSize:12,fontWeight:500,overflow:"hidden",whiteSpace:"nowrap",textOverflow:"ellipsis",color:activeId===conv.id?"var(--text)":"var(--text-2)"}}>{conv.title}</p>
                    <p style={{fontSize:10,color:"var(--text-3)",marginTop:2}}>{conv.messages.filter(m=>m.role==="user").length} messages</p>
                  </div>
                  <button onClick={e=>{e.stopPropagation();delConv(conv.id);}} style={{
                    width:20,height:20,borderRadius:6,border:"none",background:"transparent",cursor:"pointer",
                    display:"flex",alignItems:"center",justifyContent:"center",color:"var(--text-3)",opacity:0,transition:"opacity 0.15s",flexShrink:0,marginLeft:4
                  }} onMouseEnter={e=>(e.currentTarget.style.opacity="1")} onMouseLeave={e=>(e.currentTarget.style.opacity="0")}>
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>
                  </button>
                </div>
              ))}
            </div>
          )}
          {panel==="memories"&&(
            <div>
              <div style={{position:"relative",marginBottom:8}}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--text-3)" strokeWidth="1.5" strokeLinecap="round" style={{position:"absolute",left:10,top:"50%",transform:"translateY(-50%)"}}>
                  <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
                </svg>
                <input value={memSearch} onChange={e=>setMemSearch(e.target.value)} placeholder="Search memories…" style={{
                  width:"100%",background:"var(--bg-3)",border:"1px solid transparent",borderRadius:10,padding:"7px 10px 7px 28px",fontSize:12,color:"var(--text)",outline:"none",boxSizing:"border-box"
                }}/>
              </div>
              <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"0 4px",marginBottom:6}}>
                <span style={{fontSize:10,color:"var(--text-3)"}}>{filteredMems.length} memories</span>
                <button onClick={loadMems} style={{background:"none",border:"none",cursor:"pointer",color:"var(--text-3)",display:"flex",padding:2}}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" style={loadingMem?{animation:"spin 1.5s linear infinite"}:{}}>
                    <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>
                  </svg>
                </button>
              </div>
              {loadingMem&&<p style={{textAlign:"center",color:"var(--text-3)",fontSize:12,padding:"24px 0"}}>Loading…</p>}
              {!loadingMem&&filteredMems.length===0&&<p style={{textAlign:"center",color:"var(--text-3)",fontSize:12,padding:"24px 0"}}>{memSearch?"No matches":"No memories yet"}</p>}
              <div style={{display:"flex",flexDirection:"column",gap:4}}>
                {filteredMems.map(m=>(
                  <div key={m.id} style={{background:"var(--bg-3)",border:"1px solid var(--border)",borderRadius:10,padding:"10px 12px"}}
                    onMouseEnter={e=>(e.currentTarget.style.borderColor="var(--border-2)")}
                    onMouseLeave={e=>(e.currentTarget.style.borderColor="var(--border)")}>
                    <p style={{fontSize:11,color:"var(--text-2)",lineHeight:1.6,display:"-webkit-box",WebkitLineClamp:3,WebkitBoxOrient:"vertical",overflow:"hidden"}}>{m.content}</p>
                    <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginTop:6}}>
                      <span style={{fontSize:10,color:"var(--text-3)"}}>{m.created_at?timeAgo(m.created_at):""}</span>
                      <button onClick={async()=>{await api.delete(m.id);setMemories(p=>p.filter(x=>x.id!==m.id));}}
                        style={{background:"none",border:"none",cursor:"pointer",color:"var(--text-3)",fontSize:10,padding:0}}
                        onMouseEnter={e=>(e.currentTarget.style.color="var(--red)")} onMouseLeave={e=>(e.currentTarget.style.color="var(--text-3)")}>
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Sidebar footer */}
        <div style={{flexShrink:0,borderTop:"1px solid var(--border)",padding:"8px 12px"}}>
          <button onClick={()=>setShowOb(true)} style={{width:"100%",padding:"8px 12px",borderRadius:10,border:"none",background:"transparent",cursor:"pointer",textAlign:"left",fontSize:12,color:"var(--text-2)",display:"flex",alignItems:"center",gap:8}}
            onMouseEnter={e=>{(e.currentTarget as HTMLElement).style.background="var(--bg-3)";(e.currentTarget as HTMLElement).style.color="var(--text)";}}
            onMouseLeave={e=>{(e.currentTarget as HTMLElement).style.background="transparent";(e.currentTarget as HTMLElement).style.color="var(--text-2)";}}>
            ✦ Setup memories
          </button>
          {user&&(
            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"6px 12px"}}>
              <div style={{display:"flex",alignItems:"center",gap:8,minWidth:0}}>
                <div style={{width:22,height:22,borderRadius:"50%",background:"rgba(124,107,255,0.15)",display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0}}>
                  <span style={{fontSize:10,color:"var(--accent)",fontWeight:600}}>{user.username[0].toUpperCase()}</span>
                </div>
                <span style={{fontSize:12,color:"var(--text-2)",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{user.username}</span>
              </div>
              <button onClick={logout} style={{fontSize:11,color:"var(--text-3)",background:"none",border:"none",cursor:"pointer",flexShrink:0}}
                onMouseEnter={e=>(e.currentTarget.style.color="var(--red)")} onMouseLeave={e=>(e.currentTarget.style.color="var(--text-3)")}>
                Sign out
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Main */}
      <main style={{flex:1,display:"flex",flexDirection:"column",minWidth:0,minHeight:0}}>
        {/* Topbar */}
        <div style={{padding:"10px 16px",borderBottom:"1px solid var(--border)",display:"flex",alignItems:"center",justifyContent:"space-between",flexShrink:0}}>
          <div style={{display:"flex",alignItems:"center",gap:12}}>
            <button onClick={()=>setSidebar(s=>!s)} style={{width:30,height:30,borderRadius:8,border:"1px solid var(--border)",background:"transparent",cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center",color:"var(--text-2)"}}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                {sidebarOpen?<path d="M15 18l-6-6 6-6"/>:<path d="M3 6h18M3 12h18M3 18h18"/>}
              </svg>
            </button>
            <span style={{fontSize:13,color:"var(--text-2)",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",maxWidth:300}}>{activeConv?.title??"Engram"}</span>
          </div>
          <div style={{display:"flex",alignItems:"center",gap:6}}>
            <span style={{width:6,height:6,borderRadius:"50%",background:online===null?"var(--text-3)":online?"var(--green)":"var(--red)",display:"inline-block"}}/>
            <span style={{fontSize:11,color:"var(--text-3)"}}>{online===null?"connecting":online?"online":"offline"}</span>
          </div>
        </div>

        {/* Messages */}
        <div style={{flex:1,overflowY:"auto",overflowAnchor:"none"}}>
          <div style={{maxWidth:720,margin:"0 auto",padding:"32px 24px"}}>
            {messages.length===0&&(
              <div style={{display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",minHeight:"55vh",textAlign:"center",animation:"fadeIn 0.3s ease forwards"}}>
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1" strokeLinecap="round" style={{opacity:0.3,marginBottom:20}}>
                  <path d="M12 2a5 5 0 0 1 5 5v1a5 5 0 0 1-5 5 5 5 0 0 1-5-5V7a5 5 0 0 1 5-5z"/><path d="M2 18a10 10 0 0 1 20 0"/>
                </svg>
                <h2 style={{fontSize:20,fontWeight:600,marginBottom:8}}>Hello{user?`, ${user.username}`:""}</h2>
                <p style={{fontSize:14,color:"var(--text-2)",maxWidth:380,lineHeight:1.7}}>Your memories are recalled automatically. Ask me anything.</p>
              </div>
            )}
            <div style={{display:"flex",flexDirection:"column",gap:24}}>
              {messages.map(msg=>(
                <div key={msg.id} style={{display:"flex",justifyContent:msg.role==="user"?"flex-end":"flex-start",animation:"fadeIn 0.2s ease forwards"}}>
                  {msg.role==="user"?(
                    <div style={{maxWidth:"75%",background:"var(--bg-3)",border:"1px solid var(--border)",borderRadius:"18px 18px 4px 18px",padding:"12px 16px"}}>
                      <p style={{fontSize:14,lineHeight:1.7,whiteSpace:"pre-wrap"}}>{msg.content}</p>
                    </div>
                  ):(
                    <div style={{maxWidth:"88%",width:"100%"}}>
                      <div style={{display:"flex",alignItems:"flex-start",gap:12}}>
                        <div style={{width:26,height:26,borderRadius:"50%",background:"rgba(124,107,255,0.1)",border:"1px solid rgba(124,107,255,0.2)",display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0,marginTop:2}}>
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round">
                            <path d="M12 2a5 5 0 0 1 5 5v1a5 5 0 0 1-5 5 5 5 0 0 1-5-5V7a5 5 0 0 1 5-5z"/><path d="M2 18a10 10 0 0 1 20 0"/>
                          </svg>
                        </div>
                        <div style={{flex:1,minWidth:0}}>
                          {msg.isThinking?<ThinkingDots/>:
                           msg.isError?(
                             <div style={{display:"flex",gap:8,color:"var(--amber)"}}>
                               <span style={{flexShrink:0,marginTop:1}}>⚠</span>
                               <p style={{fontSize:14,lineHeight:1.7}}>{msg.content}</p>
                             </div>
                           ):(
                             <div className="prose" style={{fontSize:14,lineHeight:1.75,color:"var(--text)"}}
                               dangerouslySetInnerHTML={{__html:`<p>${renderMd(msg.content)}</p>`}}/>
                           )}
                          {!msg.isThinking&&!msg.isError&&msg.memoriesUsed!==undefined&&msg.memoriesUsed>0&&(
                            <span style={{display:"inline-block",marginTop:8,fontSize:10,color:"var(--text-3)",background:"var(--bg-3)",border:"1px solid var(--border)",padding:"2px 8px",borderRadius:99}}>
                              {msg.memoriesUsed} memor{msg.memoriesUsed===1?"y":"ies"} used
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div ref={messagesEnd} style={{height:16}}/>
          </div>
        </div>

        {/* Input */}
        <div style={{flexShrink:0,padding:"12px 24px 20px"}}>
          <div style={{maxWidth:720,margin:"0 auto"}}>
            <div style={{display:"flex",alignItems:"flex-end",gap:12,background:"var(--bg-2)",border:"1px solid var(--border)",borderRadius:20,padding:"12px 16px",transition:"border-color 0.15s"}}
              onFocus={e=>(e.currentTarget.style.borderColor="var(--border-2)")} onBlur={e=>(e.currentTarget.style.borderColor="var(--border)")}>
              <textarea ref={inputRef} value={input} onChange={e=>setInput(e.target.value)} onKeyDown={handleKey}
                placeholder="Message Engram…" rows={1} disabled={sending}
                style={{flex:1,background:"transparent",border:"none",outline:"none",resize:"none",fontSize:14,lineHeight:1.65,color:"var(--text)",fontFamily:"inherit",minHeight:24,maxHeight:160,overflow:"auto"}}/>
              <button onClick={sendMessage} disabled={!input.trim()||sending} style={{
                width:34,height:34,borderRadius:12,border:"none",cursor:input.trim()&&!sending?"pointer":"default",flexShrink:0,
                background:input.trim()&&!sending?"var(--accent)":"var(--bg-4)",
                display:"flex",alignItems:"center",justifyContent:"center",transition:"all 0.15s",opacity:!input.trim()||sending?0.35:1
              }}>
                {sending?(
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" style={{animation:"spin 1.5s linear infinite"}}>
                    <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                  </svg>
                ):(
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z"/>
                  </svg>
                )}
              </button>
            </div>
            <p style={{textAlign:"center",fontSize:10,color:"var(--text-3)",marginTop:8}}>
              Enter to send · Shift+Enter for newline
            </p>
          </div>
        </div>
      </main>

      {/* Onboarding modal */}
      {showOb&&(
        <div style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.7)",backdropFilter:"blur(4px)",display:"flex",alignItems:"center",justifyContent:"center",zIndex:50,padding:16}}
          onClick={e=>{if(e.target===e.currentTarget)setShowOb(false);}}>
          <div style={{background:"var(--bg-2)",border:"1px solid var(--border)",borderRadius:20,width:"100%",maxWidth:480,animation:"fadeIn 0.2s ease forwards",overflow:"hidden"}}>
            {obDone?(
              <div style={{padding:40,textAlign:"center"}}>
                <div style={{fontSize:28,marginBottom:16}}>✓</div>
                <h3 style={{fontSize:16,fontWeight:600,marginBottom:8}}>Memory seeded</h3>
                <p style={{fontSize:13,color:"var(--text-2)",lineHeight:1.65,marginBottom:24}}>Engram now knows you. Your memories will be recalled automatically.</p>
                <button onClick={()=>{setShowOb(false);setObDone(false);setObStep(0);}} style={{padding:"10px 24px",background:"var(--accent)",border:"none",borderRadius:12,color:"white",fontSize:13,fontWeight:500,cursor:"pointer"}}>
                  Start chatting
                </button>
              </div>
            ):(
              <div style={{padding:24}}>
                <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:20}}>
                  <div>
                    <h3 style={{fontSize:14,fontWeight:600}}>Setup memories</h3>
                    <p style={{fontSize:11,color:"var(--text-3)",marginTop:2}}>Question {obStep+1} of {OB_QUESTIONS.length}</p>
                  </div>
                  <div style={{width:80,height:4,background:"var(--bg-3)",borderRadius:99,overflow:"hidden"}}>
                    <div style={{height:"100%",background:"var(--accent)",borderRadius:99,width:`${((obStep+1)/OB_QUESTIONS.length)*100}%`,transition:"width 0.4s ease"}}/>
                  </div>
                </div>
                <p style={{fontSize:14,lineHeight:1.7,marginBottom:16,color:"var(--text)"}}>{OB_QUESTIONS[obStep]}</p>
                <textarea value={obAnswers[obStep]} onChange={e=>{const n=[...obAnswers];n[obStep]=e.target.value;setObAnswers(n);}}
                  onKeyDown={e=>{if(e.key==="Enter"&&(e.metaKey||e.ctrlKey))saveOb();}}
                  placeholder="Your answer…" rows={3} style={{
                    width:"100%",background:"var(--bg-3)",border:"1px solid var(--border)",borderRadius:12,
                    padding:"12px 14px",fontSize:13,color:"var(--text)",outline:"none",resize:"none",
                    fontFamily:"inherit",lineHeight:1.65,boxSizing:"border-box",transition:"border-color 0.15s"
                  }}/>
                <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginTop:16}}>
                  <button onClick={()=>setObStep(s=>Math.max(0,s-1))} disabled={obStep===0}
                    style={{fontSize:12,color:"var(--text-2)",background:"none",border:"none",cursor:obStep===0?"default":"pointer",opacity:obStep===0?0.3:1}}>
                    ← Back
                  </button>
                  <div style={{display:"flex",gap:8}}>
                    <button onClick={()=>setShowOb(false)} style={{padding:"8px 14px",fontSize:12,color:"var(--text-2)",background:"none",border:"none",cursor:"pointer"}}>
                      Skip
                    </button>
                    <button onClick={saveOb} disabled={!obAnswers[obStep].trim()||obSaving} style={{
                      padding:"8px 20px",background:"var(--accent)",border:"none",borderRadius:10,
                      color:"white",fontSize:12,fontWeight:500,cursor:!obAnswers[obStep].trim()||obSaving?"default":"pointer",
                      opacity:!obAnswers[obStep].trim()||obSaving?0.35:1,transition:"opacity 0.15s"
                    }}>
                      {obSaving?"Saving…":obStep===OB_QUESTIONS.length-1?"Finish →":"Next →"}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
