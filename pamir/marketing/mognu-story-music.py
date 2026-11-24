import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt
SR=48000; DUR=11.0; N=int(SR*DUR); rng=np.random.default_rng(21)
def lp(x,f): return sosfilt(butter(2,f/(SR/2),'low',output='sos'),x)
def hp(x,f): return sosfilt(butter(2,f/(SR/2),'high',output='sos'),x)
def hz(m): return 440*2**((m-69)/12)
def env(n,a=.005,r=.2): t=np.arange(n)/SR; return np.minimum(1,t/max(a,1e-4))*np.exp(-t/r)
def place(b,x,t,g=1):
    i=int(t*SR); j=min(N,i+len(x))
    if i<N: b[i:j]+=x[:j-i]*g
def tone(f,n,r=.3,a=.005,shape='sin'):
    t=np.arange(n)/SR; w=np.sin(2*np.pi*f*t) if shape=='sin' else (2*((t*f)%1)-1)
    return w*env(n,a,r)
mus=np.zeros(N); sfx=np.zeros(N)
# 0–2: сонный пад + «храп» + тиканье загрузки
n=int(2.1*SR); t=np.arange(n)/SR
pad=sum(tone(hz(m),n,9,.4) for m in (57,60,64))*.08*np.minimum(1,(2.1-t)/.3); place(mus,pad,0)
for k in (0.25,1.15):
    m=int(.7*SR); tt=np.arange(m)/SR; place(sfx,lp(rng.standard_normal(m),300)*np.sin(np.pi*tt/.7)**2*.35,k)
for k in np.arange(0.2,2.0,.25): place(sfx,hp(rng.standard_normal(600),4000)*env(600,.0005,.006)*.18,k)
# 2.05 пробуждение: «буинг»
m=int(.5*SR); tt=np.arange(m)/SR; place(sfx,np.sin(2*np.pi*np.cumsum(300+500*tt/.5)/SR)*env(m,.003,.2)*.3,2.05)
# 3.3 свист полёта молнии, 4.1 «динь» и хлопушка
m=int(.8*SR); tt=np.arange(m)/SR; place(sfx,hp(rng.standard_normal(m),1500)*np.sin(np.pi*tt/.8)**2*.2,3.3)
for mm,d in ((84,0),(88,.07),(91,.14)): place(sfx,tone(hz(mm),int(.8*SR),.35)*.22,4.1+d)
place(sfx,hp(rng.standard_normal(int(.3*SR)),800)*env(int(.3*SR),.001,.08)*.35,4.15)
# 4.1–11: весёлый бит 112 bpm, мажор
bpm=112; beat=60/bpm; t0=4.1
def kick():
    m=int(.35*SR); tt=np.arange(m)/SR; return np.sin(2*np.pi*np.cumsum(50+120*np.exp(-tt*30))/SR)*np.exp(-tt*8)
def hat(): m=int(.05*SR); return hp(rng.standard_normal(m),7000)*env(m,.0005,.015)
def clap(): m=int(.2*SR); return hp(rng.standard_normal(m),1500)*env(m,.001,.05)
chords=[(60,64,67),(57,60,64),(53,57,60),(55,59,62)]; bass=[48,45,41,43]
for i in range(40):
    tb=t0+i*beat
    if tb>DUR-.4: break
    place(mus,kick()*.7,tb)
    if i%2: place(mus,clap()*.35,tb)
    place(mus,hat()*.18,tb+beat/2)
    if i%4==0:
        c=chords[(i//4)%4]; m=int(beat*4*SR); tt=np.arange(m)/SR
        place(mus,lp(sum(tone(hz(x),m,1.2,.01,'saw') for x in c),2400)*.09,tb)
    place(mus,lp(tone(hz(bass[(i//4)%4]),int(beat*SR),.18,.004,'saw'),600)*.25,tb)
    # мелодия-«плинк»
    mel=[72,76,79,76, 72,74,76,79, 77,76,74,72, 74,76,79,84]
    place(mus,tone(hz(mel[i%16]),int(.3*SR),.12)*.12,tb+beat/2*(i%2))
# 7.6 финал: аккорд-«та-да»
for mm in (72,76,79,84): place(sfx,tone(hz(mm),int(1.6*SR),.6,.01)*.14,7.62)
fade=np.ones(N); fl=int(.8*SR); fade[-fl:]=np.linspace(1,0,fl)
out=(mus*.9+sfx)*fade; out=out/np.abs(out).max()*.9
wavfile.write('music.wav',SR,np.stack([out,out],1).astype(np.float32)); print('ok')
