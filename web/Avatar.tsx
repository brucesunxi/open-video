import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import schoolEmblem from './assets/xinghe-school-emblem.jpg';
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {VRMLoaderPlugin,VRMUtils,type VRM} from '@pixiv/three-vrm';

function SchoolEmblem(){return <span className="school-emblem" role="img" aria-label="星河实验小学校徽" style={{backgroundImage:`url(${schoolEmblem})`}}/>;}

export function Avatar({url,kind,speaking,gesture,video}:{url?:string;kind?:string;speaking:boolean;gesture:string;video?:HTMLVideoElement|null}){
  if(video)return <PortraitVideo video={video}/>;
  if(kind==='vrm' && url)return <VRMView url={url} speaking={speaking} gesture={gesture}/>;
  if(kind==='image' && url)return <div className="photo-avatar"><img src={url} alt="老师参考形象"/><SchoolEmblem/></div>;
  return <div className={`demo-avatar ${speaking?'talking':''} gesture-${gesture}`}>
    <svg viewBox="0 0 320 340" role="img" aria-label="本地演示角色，不是真实教师形象">
      <ellipse cx="160" cy="315" rx="95" ry="13" fill="#d4dfcd"/>
      <g className="body"><path d="M106 195Q160 168 214 195L228 303Q160 323 92 303Z" fill="#315c50"/>
      <path d="M143 182h34v45l-17 15-17-15Z" fill="#f0c9a9"/>
      <path d="M140 193l20 49-33-19-10-28M180 193l-20 49 33-19 10-28" fill="#fcfaf0"/>
      <g className="arm-left"><path d="M109 202Q75 215 67 259" fill="none" stroke="#315c50" strokeWidth="31" strokeLinecap="round"/><ellipse cx="64" cy="264" rx="14" ry="17" fill="#f0c9a9"/></g>
      <g className="arm-right"><path d="M209 203Q247 215 246 255" fill="none" stroke="#315c50" strokeWidth="31" strokeLinecap="round"/><ellipse cx="246" cy="260" rx="14" ry="17" fill="#f0c9a9"/></g>
      <g className="head"><path d="M101 106Q92 44 160 41Q228 42 221 113L208 153H110Z" fill="#263f37"/>
      <ellipse cx="106" cy="133" rx="12" ry="17" fill="#f0c9a9"/><ellipse cx="214" cy="133" rx="12" ry="17" fill="#f0c9a9"/>
      <path d="M111 92Q147 102 174 67Q190 88 210 92v50Q204 186 161 191Q118 184 110 143Z" fill="#f5d4b8"/>
      <g className="eyes"><ellipse cx="137" cy="126" rx="4" ry="5" fill="#344237"/><ellipse cx="184" cy="126" rx="4" ry="5" fill="#344237"/></g>
      <path d="M122 112q13-7 25-1M174 111q12-5 25 1" stroke="#344237" strokeWidth="3" fill="none"/>
      <g fill="none" stroke="#526952" strokeWidth="3"><rect x="117" y="117" width="37" height="26" rx="10"/><rect x="168" y="117" width="37" height="26" rx="10"/><path d="M154 124h14"/></g>
      <path d="M159 132l-3 16h7" stroke="#dcae8e" strokeWidth="2" fill="none"/>
      <ellipse className="mouth" cx="160" cy="164" rx="10" ry="3" fill="#9b594d"/>
      </g></g>
    </svg>
  </div>;
}

function VRMView({url,speaking,gesture}:{url:string;speaking:boolean;gesture:string}){
  const host=useRef<HTMLDivElement>(null);const latest=useRef({speaking,gesture});latest.current={speaking,gesture};
  const [error,setError]=useState('');
  useEffect(()=>{
    setError('');let disposed=false,frame=0,vrm:VRM|undefined;
    const node=host.current!;
    let renderer:THREE.WebGLRenderer;
    try{renderer=new THREE.WebGLRenderer({alpha:true,antialias:true});}catch{setError('此设备无法启动 3D 渲染。');return;}
    renderer.setPixelRatio(Math.min(devicePixelRatio,2));node.appendChild(renderer.domElement);
    const scene=new THREE.Scene();scene.add(new THREE.HemisphereLight(0xffffff,0x707b60,2.5));
    const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(1,2,3);scene.add(light);
    const camera=new THREE.PerspectiveCamera(30,1,.01,100);camera.position.set(0,1.15,3);camera.lookAt(0,1,0);
    const resize=new ResizeObserver(()=>{const w=node.clientWidth,h=node.clientHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();});resize.observe(node);
    const loader=new GLTFLoader();loader.register(parser=>new VRMLoaderPlugin(parser));
    loader.load(url,gltf=>{
      if(disposed){VRMUtils.deepDispose(gltf.scene);return;}
      vrm=gltf.userData.vrm;if(!vrm){setError('文件不包含 VRM 角色数据。');return;}
      VRMUtils.rotateVRM0(vrm);scene.add(vrm.scene);
      const box=new THREE.Box3().setFromObject(vrm.scene);const height=box.max.y-box.min.y;
      camera.position.set(0,height*.63,Math.max(2,height*1.7));camera.lookAt(0,height*.52,0);
    },undefined,()=>{if(!disposed)setError('VRM 加载失败，请检查文件或角色格式。');});
    const clock=new THREE.Clock();let elapsed=0;
    const tick=()=>{if(disposed)return;frame=requestAnimationFrame(tick);const dt=Math.min(clock.getDelta(),.05);elapsed+=dt;
      if(vrm){const active=latest.current.speaking;const em=vrm.expressionManager;
        em?.setValue('aa',active?(.2+.5*Math.abs(Math.sin(elapsed*13))):0);
        em?.setValue('blink',elapsed%4.2>.0&&elapsed%4.2<.13?1:0);
        em?.setValue('happy',latest.current.gesture==='encourage'?.4:0);
        const head=vrm.humanoid.getNormalizedBoneNode('head');if(head)head.rotation.x=active?Math.sin(elapsed*2)*.035:0;
        const left=vrm.humanoid.getNormalizedBoneNode('leftUpperArm');const right=vrm.humanoid.getNormalizedBoneNode('rightUpperArm');
        if(left)left.rotation.z=-1.1;if(right)right.rotation.z=active&&latest.current.gesture==='explain'?.75+Math.sin(elapsed)*.12:1.1;
        vrm.update(dt);
      }renderer.render(scene,camera);
    };tick();
    return()=>{disposed=true;cancelAnimationFrame(frame);resize.disconnect();if(vrm)VRMUtils.deepDispose(vrm.scene);renderer.dispose();renderer.domElement.remove();};
  },[url]);
  return <div className="vrm-wrap"><div ref={host} className="vrm-canvas"/>{error&&<div className="avatar-error">{error}</div>}</div>;
}

function PortraitVideo({video}:{video:HTMLVideoElement}){
 const host=useRef<HTMLDivElement>(null);
 useLayoutEffect(()=>{const node=host.current!;node.replaceChildren(video);return()=>{if(video.parentNode===node)node.removeChild(video);};},[video]);
 return <div className="portrait-video" aria-label="老师说话动画"><div className="portrait-media" ref={host}/><SchoolEmblem/></div>;
}
