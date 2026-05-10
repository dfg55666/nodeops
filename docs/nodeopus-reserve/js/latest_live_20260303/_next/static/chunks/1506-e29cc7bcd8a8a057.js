(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[1506],{26060:(e,t,r)=>{"use strict";function n(e){let t=e.replace(/\\/g,"/").trim();return t.startsWith("./")&&(t=t.slice(2)),t.startsWith("/")&&(t=t.slice(1)),t||"."}function i(e){let t=n(e),r=t.lastIndexOf("/");return -1===r?"":t.slice(0,r)}function s(e,t){let r=n(e).replace(/\/$/,"")||"",i=n(t),s=(r?r+"/"+i:i).split("/").filter(Boolean),o=[];for(let e of s)if("."!==e){if(".."===e){o.pop();continue}o.push(e)}return o.join("/")||"."}function o(e){let t=e.indexOf("?"),r=e.indexOf("#"),n=-1===t&&-1===r?e.length:Math.min(-1===t?e.length:t,-1===r?e.length:r);return e.slice(0,n).trim()}r.d(t,{c:()=>x});let l="https://esm.sh";function a(e){return e.startsWith("file:")||e.startsWith("workspace:")||e.startsWith("link:")?null:e.replace(/^[\^~]/,"").trim()||null}let u=["src/main.jsx","src/main.tsx","src/main.ts","main.jsx","main.tsx","main.ts","src/index.jsx","src/index.tsx","src/index.ts","index.jsx","index.tsx","index.ts"],c="18.2.0",f={react:`https://esm.sh/react@${c}`,"react/jsx-runtime":`https://esm.sh/react@${c}/jsx-runtime`,"react-dom":`https://esm.sh/react-dom@${c}?external=react`,"react-dom/client":`https://esm.sh/react-dom@${c}/client?external=react`},d={getEntry(e){let t=function(e,t){let r=new Set;for(let t of Object.keys(e))r.add(n(t));for(let e of t){let t=n(e);if(r.has(t))return t}return null}(e,u);if(!t)throw Error(`Entry file not found. Expected one of: ${u.join(", ")}`);return t},getImportMap(e){let t=function(e){let t=Object.keys(e).find(e=>"package.json"===n(e)),r=t?e[t]:void 0;if(!r)return{};try{let e=JSON.parse(r),t={...e.dependencies,...e.devDependencies};if(!t)return{};let n="react"in t,i=n?a(t.react):null,s={};for(let[e,r]of Object.entries(t)){let t=a(r);if(!t)continue;let i=`${l}/${e}@${t}`,o="react"===e,u=n&&!o?"?external=react":"";s[e]=i+u,s[e+"/"]=i+"/"+u}if(n&&i){let e=`${l}/react@${i}`;s["react/jsx-runtime"]||(s["react/jsx-runtime"]=`${e}/jsx-runtime`),s["react/jsx-dev-runtime"]||(s["react/jsx-dev-runtime"]=`${e}/jsx-dev-runtime`)}if(n&&t["react-dom"]){let e=a(t["react-dom"]);e&&!s["react-dom/client"]&&(s["react-dom/client"]=`${l}/react-dom@${e}/client?external=react`)}return s}catch{return{}}}(e);return Object.keys(t).length>0?t:{...f}},getHtmlTemplate:(e,t)=>t?function(e,t){let r=e.replace(/<script\s[^>]*(?:type\s*=\s*["']module["'][^>]*src\s*=\s*["'][^"']*["']|src\s*=\s*["'][^"']*["'][^>]*type\s*=\s*["']module["'])[^>]*>\s*<\/script>\s*/i,""),n=t.match(/<script\s+type\s*=\s*["']importmap["'][^>]*>[\s\S]*?<\/script>/i),i=n?n[0]:"",s=i?t.replace(i,"").replace(/^\s+/,""):t;if(i)if(r.includes("<head>")){let e=r.match(/<head[^>]*>/i);if(e){let t=r.indexOf(e[0])+e[0].length;r=r.slice(0,t)+`
${i}`+r.slice(t)}else r=r.replace("</head>",`${i}
</head>`)}else{let e=r.search(/<script/i);r=-1!==e?r.slice(0,e)+i+"\n"+r.slice(e):i+"\n"+r}let o=/(<div\s+id\s*=\s*["']root["'][^>]*>\s*<\/div>)/i;return o.test(r)?r.replace(o,e=>`${e}
${s}`):r.replace("</body>",`${s}
</body>`)}(t,e):`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Sandbox</title>
</head>
<body>
  <div id="root"></div>
  ${e}
</body>
</html>`},h=/\.(js|mjs|cjs)$/i,p={getEntry(e){let t=Object.keys(e).find(e=>"index.html"===n(e).toLowerCase());if(!t)throw Error("Entry file not found. Vanilla expects index.html.");let r=function(e){let t=e.match(/<script[^>]*\s+type\s*=\s*["']module["'][^>]*\s+src\s*=\s*["']([^"']+)["']|<\s*script[^>]*\s+src\s*=\s*["']([^"']+)["'][^>]*\s+type\s*=\s*["']module["']/i),r=t?.[1]??t?.[2];if(r)return n(o(r));let i=e.match(/<script[^>]+src\s*=\s*["']([^"']+)["']/i);return i?.[1]?n(o(i[1])):null}(e[t]);if(!r)return"";let l=i(t),a=s(l,r),u=Object.keys(e).map(e=>n(e)),c=new Set(u),f=function(e,t,r,n){if(n.has(e))return e;let s=e.toLowerCase(),o=r.find(e=>e.toLowerCase()===s);if(o)return o;let l=e.replace(/^.*\//,""),a=r.filter(e=>e===l||e.endsWith("/"+l));if(1===a.length)return a[0];if(a.length>1){let r=a.find(e=>i(e)===t);if(r)return r;let n=a.find(t=>t===e);return n||a[0]}let u=r.filter(e=>h.test(e));return 1===u.length?u[0]:null}(a,l,u,c);return f||""},getImportMap:e=>({}),getHtmlTemplate(e,t){if(!t)throw Error("index.html is required for Vanilla.");return t.includes("</body>")?t.replace("</body>",`${e}
</body>`):t+"\n"+e}};var m=r(38125);let g=null;async function y(e){if(g)return g;g=m.initialize({wasmURL:e??"https://unpkg.com/esbuild-wasm@0.24.2/esbuild.wasm",worker:"undefined"!=typeof Worker}),await g}async function v(e,t,r=[]){let i;await y();let s=function(e){let t=new Map;for(let[r,i]of Object.entries(e))t.set(n(r),i);return t}(e),o=s.get(t);if(!o)throw Error(`Entry file not found: ${t}`);let l=t.includes("/")?t.replace(/\/[^/]*$/,""):".",a=t.includes("/")?t.split("/").pop():t,u=t.endsWith(".tsx")||t.endsWith(".jsx")?t.endsWith(".tsx")?"tsx":"jsx":t.endsWith(".ts")?"ts":"js",c=await m.build({stdin:{contents:o,sourcefile:a,resolveDir:l,loader:u},bundle:!0,format:"esm",write:!1,outdir:".",external:r,jsx:"automatic",plugins:[{name:"virtual-fs",setup(e){e.onResolve({filter:/.*/},e=>{let t=e.resolveDir||e.importer&&e.path.startsWith(".")&&e.importer.replace(/\/[^/]*$/,"")||".";if(!(e.path.startsWith(".")||e.path.startsWith("/")))return null;let r=n(function(e,t){let r=e.replace(/\\/g,"/"),n=t.replace(/\\/g,"/");if(n.startsWith("/"))return n.slice(1);let i=[...r.split("/").filter(Boolean),...n.split("/")],s=[];for(let e of i)if("."!==e){if(".."===e){s.pop();continue}s.push(e)}return s.join("/")}(t,e.path));if(s.has(r))return{path:r,namespace:"virtual"};if(!/\.(tsx?|jsx?|mjs|cjs)$/.test(r))for(let e of[".tsx",".ts",".jsx",".js"]){let t=r+e;if(s.has(t))return{path:t,namespace:"virtual"}}for(let e of["/index.tsx","/index.ts","/index.jsx","/index.js"]){let t=r+e;if(s.has(t))return{path:t,namespace:"virtual"}}return null}),e.onLoad({filter:/.*/,namespace:"virtual"},e=>{let t,r=(t=n(e.path),s.get(t)??s.get(t+"/index.html")??null);if(null===r)return{contents:"",loader:"js"};let i=(e.path.split(".").pop()??"js").toLowerCase();return{contents:r,loader:"tsx"===i?"tsx":"ts"===i?"ts":"jsx"===i?"jsx":"css"===i?"css":"js"}})}}]}),f=c.outputFiles??[],d="",h=e=>e.replace(/\\/g,"/").toLowerCase();for(let e of f){let t=h(e.path||""),r=e.text;t.endsWith(".css")||b(r)?i=r:(t.endsWith(".js")||!b(r))&&(d=r)}if(!d){let e=c.errors?.[0];throw Error(e?.text??"Build failed: no output.")}return{bundle:d,css:i}}function b(e){let t=e.trim().slice(0,500);return!(!t.length||/\b(const|let|var|function)\s+\w|=>\s*\{|document\.|window\.|getElementById|addEventListener|\.insertAdjacentHTML|createChart|\.setData\(|createRoot|React\.|from\s+["']react|\b(import|export)\s+[\s\('"{}]/.test(t))&&!!(/^@(import|media|keyframes|charset|font-face)\s/i.test(t)||/[#\.][\w\-]+\s*\{|^[\w\-]+\s*\{\s*[a-z\-]+:\s*/.test(t))}function w(e,t,r){let i=new Map;for(let[e,r]of Object.entries(t)){let t=n(e);/\.css$/i.test(t)&&i.set(t,r)}return 0===i.size?e:e.replace(/<link\s[^>]*\/?>/gi,e=>{var t;let o,l,a,u=e.match(/\brel\s*=\s*["']([^"']+)["']/i),c=e.match(/\bhref\s*=\s*["']([^"']+)["']/i);if(u?.[1]?.toLowerCase()!=="stylesheet"||!c?.[1])return e;let f=n(s(r,(o=(t=c[1].trim()).indexOf("?"),l=t.indexOf("#"),a=-1===o&&-1===l?t.length:Math.min(-1===o?t.length:o,-1===l?t.length:l),t.slice(0,a).trim()))),d=i.get(f);if(null==d){let e=f.toLowerCase();for(let[t,r]of i)if(t.toLowerCase()===e){d=r;break}}return null!=d?`<style>${d}</style>`:e})}async function x(e){try{var t;let r,s,{files:o,framework:l}=e,a=function(e){switch(e){case"react":return d;case"vanilla":return p;default:throw Error(`Unknown framework: '${e}'. Supported: react, vanilla.`)}}(l),u=a.getEntry(o);if(""===u){let e=Object.keys(o).find(e=>"index.html"===n(e).toLowerCase()),t=e?o[e]:void 0;if(!t)throw Error("index.html not found.");let s=e?i(e):"";r=w(t,o,s)}else{let e,t,s=a.getImportMap(o),l=[...new Set(Object.keys(s).filter(e=>!e.endsWith("/")))];try{let r=await v(o,u,l);e=r.bundle,t=r.css}catch(t){let e=t instanceof Error?t.message:String(t);throw Error(`Build failed: ${e}`)}r=function(e,t,r,s,o){let l,a=Object.keys(t).length>0?`<script type="importmap">${JSON.stringify({imports:t})}</script>
`:"",u=o&&o.trim()?`<style>${o.trim().replace(/<\/style>/gi,"\\3C/style>")}</style>
`:"",c=`<script type="module">
${r}
</script>`;if(s){let e=Object.keys(s).find(e=>"index.html"===n(e).toLowerCase());e&&(l=s[e],l=w(l,s,i(e)))}return e.getHtmlTemplate(a+u+c,l)}(a,s,e,o,t)}return{url:(t=r,s=new Blob([t],{type:"text/html"}),URL.createObjectURL(s))}}catch(e){return{url:"",error:function(e){let t=e instanceof Error?e.message:String(e);if(t.includes("Unknown framework")||t.includes("Unsupported framework"))return'Unsupported framework. Choose "react" or "vanilla".';if(t.includes("Entry file not found")&&t.includes("Expected one of:"))return"No entry file found. For React, add one of: src/main.jsx, src/main.tsx, main.jsx, or main.tsx. For Vanilla, add index.html.";if(t.includes("Entry file not found")&&t.includes("Vanilla"))return"No index.html found. For Vanilla, your project must include an index.html file.";if(t.includes("Entry script not found in files"))return"The script referenced in index.html is missing from your files. Add that file or fix the script src.";if(t.includes("index.html not found"))return"index.html is missing from your project files.";if(t.includes("Could not resolve")||t.includes("resolve"))return"A file or module could not be found. Check that all imported files are included in your project.";if(t.includes("Build failed"))return t.replace(/^Build failed:\s*/i,"").trim()||"The build failed. Check your code for syntax or import errors.";if(t.includes("ERROR:")&&t.includes(":")){let e=t.match(/(?:ERROR:\s*)?([^:\n]+:\s*.+?)(?:\n|$)/),r=e?e[1].trim():t;return r.length>200?r.slice(0,197)+"…":r}return t.length>300?t.slice(0,297).trim()+"…":t.trim()||"Something went wrong. Please try again."}(e)}}}},28202:(e,t,r)=>{"use strict";function n(e,t){(null==t||t>e.length)&&(t=e.length);for(var r=0,n=Array(t);r<t;r++)n[r]=e[r];return n}function i(e,t){var r=Object.keys(e);if(Object.getOwnPropertySymbols){var n=Object.getOwnPropertySymbols(e);t&&(n=n.filter(function(t){return Object.getOwnPropertyDescriptor(e,t).enumerable})),r.push.apply(r,n)}return r}function s(e){for(var t=1;t<arguments.length;t++){var r=null!=arguments[t]?arguments[t]:{};t%2?i(Object(r),!0).forEach(function(t){var n,i;n=t,i=r[t],(n=function(e){var t=function(e,t){if("object"!=typeof e||!e)return e;var r=e[Symbol.toPrimitive];if(void 0!==r){var n=r.call(e,t);if("object"!=typeof n)return n;throw TypeError("@@toPrimitive must return a primitive value.")}return("string"===t?String:Number)(e)}(e,"string");return"symbol"==typeof t?t:t+""}(n))in e?Object.defineProperty(e,n,{value:i,enumerable:!0,configurable:!0,writable:!0}):e[n]=i}):Object.getOwnPropertyDescriptors?Object.defineProperties(e,Object.getOwnPropertyDescriptors(r)):i(Object(r)).forEach(function(t){Object.defineProperty(e,t,Object.getOwnPropertyDescriptor(r,t))})}return e}function o(e,t){var r=Object.keys(e);if(Object.getOwnPropertySymbols){var n=Object.getOwnPropertySymbols(e);t&&(n=n.filter(function(t){return Object.getOwnPropertyDescriptor(e,t).enumerable})),r.push.apply(r,n)}return r}function l(e){for(var t=1;t<arguments.length;t++){var r=null!=arguments[t]?arguments[t]:{};t%2?o(Object(r),!0).forEach(function(t){var n;n=r[t],t in e?Object.defineProperty(e,t,{value:n,enumerable:!0,configurable:!0,writable:!0}):e[t]=n}):Object.getOwnPropertyDescriptors?Object.defineProperties(e,Object.getOwnPropertyDescriptors(r)):o(Object(r)).forEach(function(t){Object.defineProperty(e,t,Object.getOwnPropertyDescriptor(r,t))})}return e}function a(e){return function t(){for(var r=this,n=arguments.length,i=Array(n),s=0;s<n;s++)i[s]=arguments[s];return i.length>=e.length?e.apply(this,i):function(){for(var e=arguments.length,n=Array(e),s=0;s<e;s++)n[s]=arguments[s];return t.apply(r,[].concat(i,n))}}}function u(e){return({}).toString.call(e).includes("Object")}function c(e){return"function"==typeof e}r.d(t,{Ay:()=>X,wG:()=>A});var f,d,h=a(function(e,t){throw Error(e[t]||e.default)})({initialIsRequired:"initial state is required",initialType:"initial state should be an object",initialContent:"initial state shouldn't be an empty object",handlerType:"handler should be an object or a function",handlersType:"all handlers should be a functions",selectorType:"selector should be a function",changeType:"provided value of changes should be an object",changeField:'it seams you want to change a field in the state which is not specified in the "initial" state',default:"an unknown error accured in `state-local` package"}),p=function(e,t){return u(t)||h("changeType"),Object.keys(t).some(function(t){return!Object.prototype.hasOwnProperty.call(e,t)})&&h("changeField"),t},m=function(e){c(e)||h("selectorType")},g=function(e){c(e)||u(e)||h("handlerType"),u(e)&&Object.values(e).some(function(e){return!c(e)})&&h("handlersType")},y=function(e){e||h("initialIsRequired"),u(e)||h("initialType"),Object.keys(e).length||h("initialContent")};function v(e,t){return c(t)?t(e.current):t}function b(e,t){return e.current=l(l({},e.current),t),t}function w(e,t,r){return c(t)?t(e.current):Object.keys(r).forEach(function(r){var n;return null==(n=t[r])?void 0:n.call(t,e.current[r])}),r}var x={configIsRequired:"the configuration object is required",configType:"the configuration object should be an object",default:"an unknown error accured in `@monaco-editor/loader` package",deprecation:"Deprecation warning!\n    You are using deprecated way of configuration.\n\n    Instead of using\n      monaco.config({ urls: { monacoBase: '...' } })\n    use\n      monaco.config({ paths: { vs: '...' } })\n\n    For more please check the link https://github.com/suren-atoyan/monaco-loader#config\n  "},E=(f=function(e,t){throw Error(e[t]||e.default)},function e(){for(var t=this,r=arguments.length,n=Array(r),i=0;i<r;i++)n[i]=arguments[i];return n.length>=f.length?f.apply(this,n):function(){for(var r=arguments.length,i=Array(r),s=0;s<r;s++)i[s]=arguments[s];return e.apply(t,[].concat(n,i))}})(x),j=function(e){return(e||E("configIsRequired"),({}).toString.call(e).includes("Object")||E("configType"),e.urls)?(console.warn(x.deprecation),{paths:{vs:e.urls.monacoBase}}):e},k=function(){for(var e=arguments.length,t=Array(e),r=0;r<e;r++)t[r]=arguments[r];return function(e){return t.reduceRight(function(e,t){return t(e)},e)}},O={type:"cancelation",msg:"operation is manually canceled"};function _(e){var t=!1,r=new Promise(function(r,n){e.then(function(e){return t?n(O):r(e)}),e.catch(n)});return r.cancel=function(){return t=!0},r}var T=["monaco"],$=function(e){if(Array.isArray(e))return e}(d=({create:function(e){var t=arguments.length>1&&void 0!==arguments[1]?arguments[1]:{};y(e),g(t);var r={current:e},n=a(w)(r,t),i=a(b)(r),s=a(p)(e),o=a(v)(r);return[function(){var e=arguments.length>0&&void 0!==arguments[0]?arguments[0]:function(e){return e};return m(e),e(r.current)},function(e){(function(){for(var e=arguments.length,t=Array(e),r=0;r<e;r++)t[r]=arguments[r];return function(e){return t.reduceRight(function(e,t){return t(e)},e)}})(n,i,s,o)(e)}]}}).create({config:{paths:{vs:"https://cdn.jsdelivr.net/npm/monaco-editor@0.55.1/min/vs"}},isInitialized:!1,resolve:null,reject:null,monaco:null}))||function(e,t){var r=null==e?null:"undefined"!=typeof Symbol&&e[Symbol.iterator]||e["@@iterator"];if(null!=r){var n,i,s,o,l=[],a=!0,u=!1;try{s=(r=r.call(e)).next,!1;for(;!(a=(n=s.call(r)).done)&&(l.push(n.value),2!==l.length);a=!0);}catch(e){u=!0,i=e}finally{try{if(!a&&null!=r.return&&(o=r.return(),Object(o)!==o))return}finally{if(u)throw i}}return l}}(d,2)||function(e,t){if(e){if("string"==typeof e)return n(e,2);var r=({}).toString.call(e).slice(8,-1);return"Object"===r&&e.constructor&&(r=e.constructor.name),"Map"===r||"Set"===r?Array.from(e):"Arguments"===r||/^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(r)?n(e,2):void 0}}(d,2)||function(){throw TypeError("Invalid attempt to destructure non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.")}(),S=$[0],P=$[1];function R(e){return document.body.appendChild(e)}function C(e){var t,r,n=S(function(e){return{config:e.config,reject:e.reject}}),i=(t="".concat(n.config.paths.vs,"/loader.js"),r=document.createElement("script"),t&&(r.src=t),r);return i.onload=function(){return e()},i.onerror=n.reject,i}function M(){var e=S(function(e){return{config:e.config,resolve:e.resolve,reject:e.reject}}),t=window.require;t.config(e.config),t(["vs/editor/editor.main"],function(t){var r=t.m||t;I(r),e.resolve(r)},function(t){e.reject(t)})}function I(e){S().monaco||P({monaco:e})}var U=new Promise(function(e,t){return P({resolve:e,reject:t})}),A={config:function(e){var t=j(e),r=t.monaco,n=function(e,t){if(null==e)return{};var r,n,i=function(e,t){if(null==e)return{};var r={};for(var n in e)if(({}).hasOwnProperty.call(e,n)){if(-1!==t.indexOf(n))continue;r[n]=e[n]}return r}(e,t);if(Object.getOwnPropertySymbols){var s=Object.getOwnPropertySymbols(e);for(n=0;n<s.length;n++)r=s[n],-1===t.indexOf(r)&&({}).propertyIsEnumerable.call(e,r)&&(i[r]=e[r])}return i}(t,T);P(function(e){return{config:function e(t,r){return Object.keys(r).forEach(function(n){r[n]instanceof Object&&t[n]&&Object.assign(r[n],e(t[n],r[n]))}),s(s({},t),r)}(e.config,n),monaco:r}})},init:function(){var e=S(function(e){return{monaco:e.monaco,isInitialized:e.isInitialized,resolve:e.resolve}});if(!e.isInitialized){if(P({isInitialized:!0}),e.monaco)return e.resolve(e.monaco),_(U);if(window.monaco&&window.monaco.editor)return I(window.monaco),e.resolve(window.monaco),_(U);k(R,C)(M)}return _(U)},__getMonacoInstance:function(){return S(function(e){return e.monaco})}},D=r(12115),N={display:"flex",position:"relative",textAlign:"initial"},F={width:"100%"},V={display:"none"},L={display:"flex",height:"100%",width:"100%",justifyContent:"center",alignItems:"center"},W=function({children:e}){return D.createElement("div",{style:L},e)},B=(0,D.memo)(function({width:e,height:t,isEditorReady:r,loading:n,_ref:i,className:s,wrapperProps:o}){return D.createElement("section",{style:{...N,width:e,height:t},...o},!r&&D.createElement(W,null,n),D.createElement("div",{ref:i,style:{...F,...!r&&V},className:s}))}),z=function(e){(0,D.useEffect)(e,[])},q=function(e,t,r=!0){let n=(0,D.useRef)(!0);(0,D.useEffect)(n.current||!r?()=>{n.current=!1}:e,t)};function G(){}function Y(e,t,r,n){var i,s,o,l,a,u;return i=e,s=n,i.editor.getModel(H(i,s))||(o=e,l=t,a=r,u=n,o.editor.createModel(l,a,u?H(o,u):void 0))}function H(e,t){return e.Uri.parse(t)}(0,D.memo)(function({original:e,modified:t,language:r,originalLanguage:n,modifiedLanguage:i,originalModelPath:s,modifiedModelPath:o,keepCurrentOriginalModel:l=!1,keepCurrentModifiedModel:a=!1,theme:u="light",loading:c="Loading...",options:f={},height:d="100%",width:h="100%",className:p,wrapperProps:m={},beforeMount:g=G,onMount:y=G}){let[v,b]=(0,D.useState)(!1),[w,x]=(0,D.useState)(!0),E=(0,D.useRef)(null),j=(0,D.useRef)(null),k=(0,D.useRef)(null),O=(0,D.useRef)(y),_=(0,D.useRef)(g),T=(0,D.useRef)(!1);z(()=>{let e=A.init();return e.then(e=>(j.current=e)&&x(!1)).catch(e=>e?.type!=="cancelation"&&console.error("Monaco initialization: error:",e)),()=>{let t;return E.current?(t=E.current?.getModel(),void(l||t?.original?.dispose(),a||t?.modified?.dispose(),E.current?.dispose())):e.cancel()}}),q(()=>{if(E.current&&j.current){let t=E.current.getOriginalEditor(),i=Y(j.current,e||"",n||r||"text",s||"");i!==t.getModel()&&t.setModel(i)}},[s],v),q(()=>{if(E.current&&j.current){let e=E.current.getModifiedEditor(),n=Y(j.current,t||"",i||r||"text",o||"");n!==e.getModel()&&e.setModel(n)}},[o],v),q(()=>{let e=E.current.getModifiedEditor();e.getOption(j.current.editor.EditorOption.readOnly)?e.setValue(t||""):t!==e.getValue()&&(e.executeEdits("",[{range:e.getModel().getFullModelRange(),text:t||"",forceMoveMarkers:!0}]),e.pushUndoStop())},[t],v),q(()=>{E.current?.getModel()?.original.setValue(e||"")},[e],v),q(()=>{let{original:e,modified:t}=E.current.getModel();j.current.editor.setModelLanguage(e,n||r||"text"),j.current.editor.setModelLanguage(t,i||r||"text")},[r,n,i],v),q(()=>{j.current?.editor.setTheme(u)},[u],v),q(()=>{E.current?.updateOptions(f)},[f],v);let $=(0,D.useCallback)(()=>{if(!j.current)return;_.current(j.current);let l=Y(j.current,e||"",n||r||"text",s||""),a=Y(j.current,t||"",i||r||"text",o||"");E.current?.setModel({original:l,modified:a})},[r,t,i,e,n,s,o]),S=(0,D.useCallback)(()=>{!T.current&&k.current&&(E.current=j.current.editor.createDiffEditor(k.current,{automaticLayout:!0,...f}),$(),j.current?.editor.setTheme(u),b(!0),T.current=!0)},[f,u,$]);return(0,D.useEffect)(()=>{v&&O.current(E.current,j.current)},[v]),(0,D.useEffect)(()=>{w||v||S()},[w,v,S]),D.createElement(B,{width:h,height:d,isEditorReady:v,loading:c,_ref:k,className:p,wrapperProps:m})});var J=function(e){let t=(0,D.useRef)();return(0,D.useEffect)(()=>{t.current=e},[e]),t.current},K=new Map,X=(0,D.memo)(function({defaultValue:e,defaultLanguage:t,defaultPath:r,value:n,language:i,path:s,theme:o="light",line:l,loading:a="Loading...",options:u={},overrideServices:c={},saveViewState:f=!0,keepCurrentModel:d=!1,width:h="100%",height:p="100%",className:m,wrapperProps:g={},beforeMount:y=G,onMount:v=G,onChange:b,onValidate:w=G}){let[x,E]=(0,D.useState)(!1),[j,k]=(0,D.useState)(!0),O=(0,D.useRef)(null),_=(0,D.useRef)(null),T=(0,D.useRef)(null),$=(0,D.useRef)(v),S=(0,D.useRef)(y),P=(0,D.useRef)(),R=(0,D.useRef)(n),C=J(s),M=(0,D.useRef)(!1),I=(0,D.useRef)(!1);z(()=>{let e=A.init();return e.then(e=>(O.current=e)&&k(!1)).catch(e=>e?.type!=="cancelation"&&console.error("Monaco initialization: error:",e)),()=>_.current?void(P.current?.dispose(),d?f&&K.set(s,_.current.saveViewState()):_.current.getModel()?.dispose(),_.current.dispose()):e.cancel()}),q(()=>{let o=Y(O.current,e||n||"",t||i||"",s||r||"");o!==_.current?.getModel()&&(f&&K.set(C,_.current?.saveViewState()),_.current?.setModel(o),f&&_.current?.restoreViewState(K.get(s)))},[s],x),q(()=>{_.current?.updateOptions(u)},[u],x),q(()=>{_.current&&void 0!==n&&(_.current.getOption(O.current.editor.EditorOption.readOnly)?_.current.setValue(n):n!==_.current.getValue()&&(I.current=!0,_.current.executeEdits("",[{range:_.current.getModel().getFullModelRange(),text:n,forceMoveMarkers:!0}]),_.current.pushUndoStop(),I.current=!1))},[n],x),q(()=>{let e=_.current?.getModel();e&&i&&O.current?.editor.setModelLanguage(e,i)},[i],x),q(()=>{void 0!==l&&_.current?.revealLine(l)},[l],x),q(()=>{O.current?.editor.setTheme(o)},[o],x);let U=(0,D.useCallback)(()=>{if(!(!T.current||!O.current)&&!M.current){S.current(O.current);let a=s||r,d=Y(O.current,n||e||"",t||i||"",a||"");_.current=O.current?.editor.create(T.current,{model:d,automaticLayout:!0,...u},c),f&&_.current.restoreViewState(K.get(a)),O.current.editor.setTheme(o),void 0!==l&&_.current.revealLine(l),E(!0),M.current=!0}},[e,t,r,n,i,s,u,c,f,o,l]);return(0,D.useEffect)(()=>{x&&$.current(_.current,O.current)},[x]),(0,D.useEffect)(()=>{j||x||U()},[j,x,U]),R.current=n,(0,D.useEffect)(()=>{x&&b&&(P.current?.dispose(),P.current=_.current?.onDidChangeModelContent(e=>{I.current||b(_.current.getValue(),e)}))},[x,b]),(0,D.useEffect)(()=>{if(x){let e=O.current.editor.onDidChangeMarkers(e=>{let t=_.current.getModel()?.uri;if(t&&e.find(e=>e.path===t.path)){let e=O.current.editor.getModelMarkers({resource:t});w?.(e)}});return()=>{e?.dispose()}}return()=>{}},[x,w]),D.createElement(B,{width:h,height:p,isEditorReady:x,loading:a,_ref:T,className:m,wrapperProps:g})})},38125:(e,t,r)=>{e=r.nmd(e);var n=r(49304).hp;(e=>{"use strict";var t,r,i,s,o,l,a=Object.defineProperty,u=Object.getOwnPropertyDescriptor,c=Object.getOwnPropertyNames,f=Object.prototype.hasOwnProperty,d=(e,t,r)=>new Promise((n,i)=>{var s=e=>{try{l(r.next(e))}catch(e){i(e)}},o=e=>{try{l(r.throw(e))}catch(e){i(e)}},l=e=>e.done?n(e.value):Promise.resolve(e.value).then(s,o);l((r=r.apply(e,t)).next())}),h={},p={analyzeMetafile:()=>el,analyzeMetafileSync:()=>ef,build:()=>en,buildSync:()=>ea,context:()=>ei,default:()=>eg,formatMessages:()=>eo,formatMessagesSync:()=>ec,initialize:()=>ep,stop:()=>ed,transform:()=>es,transformSync:()=>eu,version:()=>er};for(var m in p)a(h,m,{get:p[m],enumerable:!0});function g(e){let r=e=>{if(null===e)n.write8(0);else if("boolean"==typeof e)n.write8(1),n.write8(+e);else if("number"==typeof e)n.write8(2),n.write32(0|e);else if("string"==typeof e)n.write8(3),n.write(t(e));else if(e instanceof Uint8Array)n.write8(4),n.write(e);else if(e instanceof Array)for(let t of(n.write8(5),n.write32(e.length),e))r(t);else{let i=Object.keys(e);for(let s of(n.write8(6),n.write32(i.length),i))n.write(t(s)),r(e[s])}},n=new y;return n.write32(0),n.write32(e.id<<1|!e.isRequest),r(e.value),b(n.buf,n.len-4,0),n.buf.subarray(0,n.len)}e.exports=((e,t,r,n)=>{if(t&&"object"==typeof t||"function"==typeof t)for(let i of c(t))f.call(e,i)||i===r||a(e,i,{get:()=>t[i],enumerable:!(n=u(t,i))||n.enumerable});return e})(a({},"__esModule",{value:!0}),h);var y=class{constructor(e=new Uint8Array(1024)){this.buf=e,this.len=0,this.ptr=0}_write(e){if(this.len+e>this.buf.length){let t=new Uint8Array((this.len+e)*2);t.set(this.buf),this.buf=t}return this.len+=e,this.len-e}write8(e){let t=this._write(1);this.buf[t]=e}write32(e){let t=this._write(4);b(this.buf,e,t)}write(e){let t=this._write(4+e.length);b(this.buf,e.length,t),this.buf.set(e,t+4)}_read(e){if(this.ptr+e>this.buf.length)throw Error("Invalid packet");return this.ptr+=e,this.ptr-e}read8(){return this.buf[this._read(1)]}read32(){return v(this.buf,this._read(4))}read(){let e=this.read32(),t=new Uint8Array(e),r=this._read(t.length);return t.set(this.buf.subarray(r,r+e)),t}};if("undefined"!=typeof TextEncoder&&"undefined"!=typeof TextDecoder){let e=new TextEncoder,n=new TextDecoder;t=t=>e.encode(t),r=e=>n.decode(e),i='new TextEncoder().encode("")'}else if(void 0!==n)t=e=>n.from(e),r=e=>{let{buffer:t,byteOffset:r,byteLength:i}=e;return n.from(t,r,i).toString()},i='Buffer.from("")';else throw Error("No UTF-8 codec found");if(!(t("")instanceof Uint8Array))throw Error(`Invariant violation: "${i} instanceof Uint8Array" is incorrectly false

This indicates that your JavaScript environment is broken. You cannot use
esbuild in this environment because esbuild relies on this invariant. This
is not a problem with esbuild. You need to fix your environment instead.
`);function v(e,t){return e[t++]|e[t++]<<8|e[t++]<<16|e[t++]<<24}function b(e,t,r){e[r++]=t,e[r++]=t>>8,e[r++]=t>>16,e[r++]=t>>24}var w=JSON.stringify,x="warning",E="silent";function j(e){if(z(e,"target"),e.indexOf(",")>=0)throw Error(`Invalid target: ${e}`);return e}var k=()=>null,O=e=>"boolean"==typeof e?null:"a boolean",_=e=>"string"==typeof e?null:"a string",T=e=>e instanceof RegExp?null:"a RegExp object",$=e=>"number"==typeof e&&e===(0|e)?null:"an integer",S=e=>"function"==typeof e?null:"a function",P=e=>Array.isArray(e)?null:"an array",R=e=>"object"!=typeof e||null===e||Array.isArray(e)?"an object":null,C=e=>"object"==typeof e&&null!==e?null:"an array or an object",M=e=>e instanceof WebAssembly.Module?null:"a WebAssembly.Module",I=e=>"object"!=typeof e||Array.isArray(e)?"an object or null":null,U=e=>"string"==typeof e||"boolean"==typeof e?null:"a string or a boolean",A=e=>"string"!=typeof e&&("object"!=typeof e||null===e||Array.isArray(e))?"a string or an object":null,D=e=>"string"==typeof e||Array.isArray(e)?null:"a string or an array",N=e=>"string"==typeof e||e instanceof Uint8Array?null:"a string or a Uint8Array",F=e=>"string"==typeof e||e instanceof URL?null:"a string or a URL";function V(e,t,r,n){let i=e[r];if(t[r+""]=!0,void 0===i)return;let s=n(i);if(null!==s)throw Error(`${w(r)} must be ${s}`);return i}function L(e,t,r){for(let n in e)if(!(n in t))throw Error(`Invalid option ${r}: ${w(n)}`)}function W(e){let t;if(void 0!==e)for(let r in t=Object.create(null),e){let n=e[r];if("string"==typeof n||!1===n)t[r]=n;else throw Error(`Expected ${w(r)} in mangle cache to map to either a string or false`)}return t}function B(e,t,r,n,i){let s=V(t,r,"color",O),o=V(t,r,"logLevel",_),l=V(t,r,"logLimit",$);void 0!==s?e.push(`--color=${s}`):n&&e.push("--color=true"),e.push(`--log-level=${o||i}`),e.push(`--log-limit=${l||0}`)}function z(e,t,r){if("string"!=typeof e)throw Error(`Expected value for ${t}${void 0!==r?" "+w(r):""} to be a string, got ${typeof e} instead`);return e}function q(e,t,r){let n=V(t,r,"legalComments",_),i=V(t,r,"sourceRoot",_),s=V(t,r,"sourcesContent",O),o=V(t,r,"target",D),l=V(t,r,"format",_),a=V(t,r,"globalName",_),u=V(t,r,"mangleProps",T),c=V(t,r,"reserveProps",T),f=V(t,r,"mangleQuoted",O),d=V(t,r,"minify",O),h=V(t,r,"minifySyntax",O),p=V(t,r,"minifyWhitespace",O),m=V(t,r,"minifyIdentifiers",O),g=V(t,r,"lineLimit",$),y=V(t,r,"drop",P),v=V(t,r,"dropLabels",P),b=V(t,r,"charset",_),x=V(t,r,"treeShaking",O),E=V(t,r,"ignoreAnnotations",O),k=V(t,r,"jsx",_),S=V(t,r,"jsxFactory",_),C=V(t,r,"jsxFragment",_),M=V(t,r,"jsxImportSource",_),I=V(t,r,"jsxDev",O),U=V(t,r,"jsxSideEffects",O),N=V(t,r,"define",R),F=V(t,r,"logOverride",R),L=V(t,r,"supported",R),W=V(t,r,"pure",P),B=V(t,r,"keepNames",O),q=V(t,r,"platform",_),G=V(t,r,"tsconfigRaw",A);if(n&&e.push(`--legal-comments=${n}`),void 0!==i&&e.push(`--source-root=${i}`),void 0!==s&&e.push(`--sources-content=${s}`),o&&(Array.isArray(o)?e.push(`--target=${Array.from(o).map(j).join(",")}`):e.push(`--target=${j(o)}`)),l&&e.push(`--format=${l}`),a&&e.push(`--global-name=${a}`),q&&e.push(`--platform=${q}`),G&&e.push(`--tsconfig-raw=${"string"==typeof G?G:JSON.stringify(G)}`),d&&e.push("--minify"),h&&e.push("--minify-syntax"),p&&e.push("--minify-whitespace"),m&&e.push("--minify-identifiers"),g&&e.push(`--line-limit=${g}`),b&&e.push(`--charset=${b}`),void 0!==x&&e.push(`--tree-shaking=${x}`),E&&e.push("--ignore-annotations"),y)for(let t of y)e.push(`--drop:${z(t,"drop")}`);if(v&&e.push(`--drop-labels=${Array.from(v).map(e=>z(e,"dropLabels")).join(",")}`),u&&e.push(`--mangle-props=${u.source}`),c&&e.push(`--reserve-props=${c.source}`),void 0!==f&&e.push(`--mangle-quoted=${f}`),k&&e.push(`--jsx=${k}`),S&&e.push(`--jsx-factory=${S}`),C&&e.push(`--jsx-fragment=${C}`),M&&e.push(`--jsx-import-source=${M}`),I&&e.push("--jsx-dev"),U&&e.push("--jsx-side-effects"),N)for(let t in N){if(t.indexOf("=")>=0)throw Error(`Invalid define: ${t}`);e.push(`--define:${t}=${z(N[t],"define",t)}`)}if(F)for(let t in F){if(t.indexOf("=")>=0)throw Error(`Invalid log override: ${t}`);e.push(`--log-override:${t}=${z(F[t],"log override",t)}`)}if(L)for(let t in L){if(t.indexOf("=")>=0)throw Error(`Invalid supported: ${t}`);let r=L[t];if("boolean"!=typeof r)throw Error(`Expected value for supported ${w(t)} to be a boolean, got ${typeof r} instead`);e.push(`--supported:${t}=${r}`)}if(W)for(let t of W)e.push(`--pure:${z(t,"pure")}`);B&&e.push("--keep-names")}function G(){let e=new Map,t=0;return{clear(){e.clear()},load:t=>e.get(t),store(r){if(void 0===r)return -1;let n=t++;return e.set(n,r),n}}}function Y(e,t,r){let n,i=!1;return()=>{if(i)return n;i=!0;try{let i=(e.stack+"").split("\n");i.splice(1,1);let s=J(t,i,r);if(s)return n={text:e.message,location:s}}catch(e){}}}function H(e,t,r,n,i){let s="Internal error",o=null;try{s=(e&&e.message||e)+""}catch(e){}try{o=J(t,(e.stack+"").split("\n"),"")}catch(e){}return{id:"",pluginName:i,text:s,location:o,notes:n?[n]:[],detail:r?r.store(e):-1}}function J(e,r,n){let i="    at ";if(e.readFileSync&&!r[0].startsWith(i)&&r[1].startsWith(i))for(let s=1;s<r.length;s++){let o=r[s];if(o.startsWith(i))for(o=o.slice(i.length);;){let i=/^(?:new |async )?\S+ \((.*)\)$/.exec(o);if(i||(i=/^eval at \S+ \((.*)\)(?:, \S+:\d+:\d+)?$/.exec(o))){o=i[1];continue}if(i=/^(\S+):(\d+):(\d+)$/.exec(o)){let s;try{s=e.readFileSync(i[1],"utf8")}catch(e){break}let o=s.split(/\r\n|\r|\n|\u2028|\u2029/)[i[2]-1]||"",l=i[3]-1,a=o.slice(l,l+n.length)===n?n.length:0;return{file:i[1],namespace:"file",line:+i[2],column:t(o.slice(0,l)).length,length:t(o.slice(l,l+a)).length,lineText:o+"\n"+r.slice(1).join("\n"),suggestion:""}}break}}return null}function K(e,t,r){let n=Error(e+=t.length<1?"":` with ${t.length} error${t.length<2?"":"s"}:`+t.slice(0,6).map((e,t)=>{if(5===t)return"\n...";if(!e.location)return`
error: ${e.text}`;let{file:r,line:n,column:i}=e.location,s=e.pluginName?`[plugin: ${e.pluginName}] `:"";return`
${r}:${n}:${i}: ERROR: ${s}${e.text}`}).join(""));for(let[e,i]of[["errors",t],["warnings",r]])Object.defineProperty(n,e,{configurable:!0,enumerable:!0,get:()=>i,set:t=>Object.defineProperty(n,e,{configurable:!0,enumerable:!0,value:t})});return n}function X(e,t){for(let r of e)r.detail=t.load(r.detail);return e}function Q(e,t,r){if(null==e)return null;let n={},i=V(e,n,"file",_),s=V(e,n,"namespace",_),o=V(e,n,"line",$),l=V(e,n,"column",$),a=V(e,n,"length",$),u=V(e,n,"lineText",_),c=V(e,n,"suggestion",_);if(L(e,n,t),u){let e=u.slice(0,(l&&l>0?l:0)+(a&&a>0?a:0)+(r&&r>0?r:80));/[\x7F-\uFFFF]/.test(e)||/\n/.test(u)||(u=e)}return{file:i||"",namespace:s||"",line:o||0,column:l||0,length:a||0,lineText:u||"",suggestion:c||""}}function Z(e,t,r,n,i){let s=[],o=0;for(let l of e){let e={},a=V(l,e,"id",_),u=V(l,e,"pluginName",_),c=V(l,e,"text",_),f=V(l,e,"location",I),d=V(l,e,"notes",P),h=V(l,e,"detail",k),p=`in element ${o} of "${t}"`;L(l,e,p);let m=[];if(d)for(let e of d){let t={},r=V(e,t,"text",_),n=V(e,t,"location",I);L(e,t,p),m.push({text:r||"",location:Q(n,p,i)})}s.push({id:a||"",pluginName:u||n,text:c||"",location:Q(f,p,i),notes:m,detail:r?r.store(h):-1}),o++}return s}function ee(e,t){let r=[];for(let n of e){if("string"!=typeof n)throw Error(`${w(t)} must be an array of strings`);r.push(n)}return r}function et({path:e,contents:t,hash:n}){let i=null;return{path:e,contents:t,hash:n,get text(){let e=this.contents;return(null===i||e!==t)&&(t=e,i=r(e)),i}}}var er="0.24.2",en=e=>eh().build(e),ei=e=>eh().context(e),es=(e,t)=>eh().transform(e,t),eo=(e,t)=>eh().formatMessages(e,t),el=(e,t)=>eh().analyzeMetafile(e,t),ea=()=>{throw Error('The "buildSync" API only works in node')},eu=()=>{throw Error('The "transformSync" API only works in node')},ec=()=>{throw Error('The "formatMessagesSync" API only works in node')},ef=()=>{throw Error('The "analyzeMetafileSync" API only works in node')},ed=()=>(o&&o(),Promise.resolve()),eh=()=>{if(l)return l;if(s)throw Error('You need to wait for the promise returned from "initialize" to be resolved before calling this');throw Error('You need to call "initialize" before calling this')},ep=e=>{var t;let r,n,i,o;n=V(t=e||{},r=Object.create(null),"wasmURL",F),i=V(t,r,"wasmModule",M),o=V(t,r,"worker",O),L(t,r,"in initialize() call");let l=(e={wasmURL:n,wasmModule:i,worker:o}).wasmURL,a=e.wasmModule,u=!1!==e.worker;if(!l&&!a)throw Error('Must provide either the "wasmURL" option or the "wasmModule" option');if(s)throw Error('Cannot call "initialize" more than once');return(s=em(l||"",a,u)).catch(()=>{s=void 0}),s},em=(e,n,i)=>d(void 0,null,function*(){let a,u,c,f,p=new Promise(e=>u=e);if(i){let e=new Blob([`onmessage=((postMessage) => {
      // Copyright 2018 The Go Authors. All rights reserved.
      // Use of this source code is governed by a BSD-style
      // license that can be found in the LICENSE file.
      var __async = (__this, __arguments, generator) => {
        return new Promise((resolve, reject) => {
          var fulfilled = (value) => {
            try {
              step(generator.next(value));
            } catch (e) {
              reject(e);
            }
          };
          var rejected = (value) => {
            try {
              step(generator.throw(value));
            } catch (e) {
              reject(e);
            }
          };
          var step = (x) => x.done ? resolve(x.value) : Promise.resolve(x.value).then(fulfilled, rejected);
          step((generator = generator.apply(__this, __arguments)).next());
        });
      };
      let onmessage;
      let globalThis = {};
      for (let o = self; o; o = Object.getPrototypeOf(o))
        for (let k of Object.getOwnPropertyNames(o))
          if (!(k in globalThis))
            Object.defineProperty(globalThis, k, { get: () => self[k] });
      "use strict";
      (() => {
        const enosys = () => {
          const err = new Error("not implemented");
          err.code = "ENOSYS";
          return err;
        };
        if (!globalThis.fs) {
          let outputBuf = "";
          globalThis.fs = {
            constants: { O_WRONLY: -1, O_RDWR: -1, O_CREAT: -1, O_TRUNC: -1, O_APPEND: -1, O_EXCL: -1 },
            // unused
            writeSync(fd, buf) {
              outputBuf += decoder.decode(buf);
              const nl = outputBuf.lastIndexOf("\\n");
              if (nl != -1) {
                console.log(outputBuf.substring(0, nl));
                outputBuf = outputBuf.substring(nl + 1);
              }
              return buf.length;
            },
            write(fd, buf, offset, length, position, callback) {
              if (offset !== 0 || length !== buf.length || position !== null) {
                callback(enosys());
                return;
              }
              const n = this.writeSync(fd, buf);
              callback(null, n);
            },
            chmod(path, mode, callback) {
              callback(enosys());
            },
            chown(path, uid, gid, callback) {
              callback(enosys());
            },
            close(fd, callback) {
              callback(enosys());
            },
            fchmod(fd, mode, callback) {
              callback(enosys());
            },
            fchown(fd, uid, gid, callback) {
              callback(enosys());
            },
            fstat(fd, callback) {
              callback(enosys());
            },
            fsync(fd, callback) {
              callback(null);
            },
            ftruncate(fd, length, callback) {
              callback(enosys());
            },
            lchown(path, uid, gid, callback) {
              callback(enosys());
            },
            link(path, link, callback) {
              callback(enosys());
            },
            lstat(path, callback) {
              callback(enosys());
            },
            mkdir(path, perm, callback) {
              callback(enosys());
            },
            open(path, flags, mode, callback) {
              callback(enosys());
            },
            read(fd, buffer, offset, length, position, callback) {
              callback(enosys());
            },
            readdir(path, callback) {
              callback(enosys());
            },
            readlink(path, callback) {
              callback(enosys());
            },
            rename(from, to, callback) {
              callback(enosys());
            },
            rmdir(path, callback) {
              callback(enosys());
            },
            stat(path, callback) {
              callback(enosys());
            },
            symlink(path, link, callback) {
              callback(enosys());
            },
            truncate(path, length, callback) {
              callback(enosys());
            },
            unlink(path, callback) {
              callback(enosys());
            },
            utimes(path, atime, mtime, callback) {
              callback(enosys());
            }
          };
        }
        if (!globalThis.process) {
          globalThis.process = {
            getuid() {
              return -1;
            },
            getgid() {
              return -1;
            },
            geteuid() {
              return -1;
            },
            getegid() {
              return -1;
            },
            getgroups() {
              throw enosys();
            },
            pid: -1,
            ppid: -1,
            umask() {
              throw enosys();
            },
            cwd() {
              throw enosys();
            },
            chdir() {
              throw enosys();
            }
          };
        }
        if (!globalThis.crypto) {
          throw new Error("globalThis.crypto is not available, polyfill required (crypto.getRandomValues only)");
        }
        if (!globalThis.performance) {
          throw new Error("globalThis.performance is not available, polyfill required (performance.now only)");
        }
        if (!globalThis.TextEncoder) {
          throw new Error("globalThis.TextEncoder is not available, polyfill required");
        }
        if (!globalThis.TextDecoder) {
          throw new Error("globalThis.TextDecoder is not available, polyfill required");
        }
        const encoder = new TextEncoder("utf-8");
        const decoder = new TextDecoder("utf-8");
        globalThis.Go = class {
          constructor() {
            this.argv = ["js"];
            this.env = {};
            this.exit = (code) => {
              if (code !== 0) {
                console.warn("exit code:", code);
              }
            };
            this._exitPromise = new Promise((resolve) => {
              this._resolveExitPromise = resolve;
            });
            this._pendingEvent = null;
            this._scheduledTimeouts = /* @__PURE__ */ new Map();
            this._nextCallbackTimeoutID = 1;
            const setInt64 = (addr, v) => {
              this.mem.setUint32(addr + 0, v, true);
              this.mem.setUint32(addr + 4, Math.floor(v / 4294967296), true);
            };
            const setInt32 = (addr, v) => {
              this.mem.setUint32(addr + 0, v, true);
            };
            const getInt64 = (addr) => {
              const low = this.mem.getUint32(addr + 0, true);
              const high = this.mem.getInt32(addr + 4, true);
              return low + high * 4294967296;
            };
            const loadValue = (addr) => {
              const f = this.mem.getFloat64(addr, true);
              if (f === 0) {
                return void 0;
              }
              if (!isNaN(f)) {
                return f;
              }
              const id = this.mem.getUint32(addr, true);
              return this._values[id];
            };
            const storeValue = (addr, v) => {
              const nanHead = 2146959360;
              if (typeof v === "number" && v !== 0) {
                if (isNaN(v)) {
                  this.mem.setUint32(addr + 4, nanHead, true);
                  this.mem.setUint32(addr, 0, true);
                  return;
                }
                this.mem.setFloat64(addr, v, true);
                return;
              }
              if (v === void 0) {
                this.mem.setFloat64(addr, 0, true);
                return;
              }
              let id = this._ids.get(v);
              if (id === void 0) {
                id = this._idPool.pop();
                if (id === void 0) {
                  id = this._values.length;
                }
                this._values[id] = v;
                this._goRefCounts[id] = 0;
                this._ids.set(v, id);
              }
              this._goRefCounts[id]++;
              let typeFlag = 0;
              switch (typeof v) {
                case "object":
                  if (v !== null) {
                    typeFlag = 1;
                  }
                  break;
                case "string":
                  typeFlag = 2;
                  break;
                case "symbol":
                  typeFlag = 3;
                  break;
                case "function":
                  typeFlag = 4;
                  break;
              }
              this.mem.setUint32(addr + 4, nanHead | typeFlag, true);
              this.mem.setUint32(addr, id, true);
            };
            const loadSlice = (addr) => {
              const array = getInt64(addr + 0);
              const len = getInt64(addr + 8);
              return new Uint8Array(this._inst.exports.mem.buffer, array, len);
            };
            const loadSliceOfValues = (addr) => {
              const array = getInt64(addr + 0);
              const len = getInt64(addr + 8);
              const a = new Array(len);
              for (let i = 0; i < len; i++) {
                a[i] = loadValue(array + i * 8);
              }
              return a;
            };
            const loadString = (addr) => {
              const saddr = getInt64(addr + 0);
              const len = getInt64(addr + 8);
              return decoder.decode(new DataView(this._inst.exports.mem.buffer, saddr, len));
            };
            const timeOrigin = Date.now() - performance.now();
            this.importObject = {
              _gotest: {
                add: (a, b) => a + b
              },
              gojs: {
                // Go's SP does not change as long as no Go code is running. Some operations (e.g. calls, getters and setters)
                // may synchronously trigger a Go event handler. This makes Go code get executed in the middle of the imported
                // function. A goroutine can switch to a new stack if the current stack is too small (see morestack function).
                // This changes the SP, thus we have to update the SP used by the imported function.
                // func wasmExit(code int32)
                "runtime.wasmExit": (sp) => {
                  sp >>>= 0;
                  const code = this.mem.getInt32(sp + 8, true);
                  this.exited = true;
                  delete this._inst;
                  delete this._values;
                  delete this._goRefCounts;
                  delete this._ids;
                  delete this._idPool;
                  this.exit(code);
                },
                // func wasmWrite(fd uintptr, p unsafe.Pointer, n int32)
                "runtime.wasmWrite": (sp) => {
                  sp >>>= 0;
                  const fd = getInt64(sp + 8);
                  const p = getInt64(sp + 16);
                  const n = this.mem.getInt32(sp + 24, true);
                  globalThis.fs.writeSync(fd, new Uint8Array(this._inst.exports.mem.buffer, p, n));
                },
                // func resetMemoryDataView()
                "runtime.resetMemoryDataView": (sp) => {
                  sp >>>= 0;
                  this.mem = new DataView(this._inst.exports.mem.buffer);
                },
                // func nanotime1() int64
                "runtime.nanotime1": (sp) => {
                  sp >>>= 0;
                  setInt64(sp + 8, (timeOrigin + performance.now()) * 1e6);
                },
                // func walltime() (sec int64, nsec int32)
                "runtime.walltime": (sp) => {
                  sp >>>= 0;
                  const msec = (/* @__PURE__ */ new Date()).getTime();
                  setInt64(sp + 8, msec / 1e3);
                  this.mem.setInt32(sp + 16, msec % 1e3 * 1e6, true);
                },
                // func scheduleTimeoutEvent(delay int64) int32
                "runtime.scheduleTimeoutEvent": (sp) => {
                  sp >>>= 0;
                  const id = this._nextCallbackTimeoutID;
                  this._nextCallbackTimeoutID++;
                  this._scheduledTimeouts.set(id, setTimeout(
                    () => {
                      this._resume();
                      while (this._scheduledTimeouts.has(id)) {
                        console.warn("scheduleTimeoutEvent: missed timeout event");
                        this._resume();
                      }
                    },
                    getInt64(sp + 8)
                  ));
                  this.mem.setInt32(sp + 16, id, true);
                },
                // func clearTimeoutEvent(id int32)
                "runtime.clearTimeoutEvent": (sp) => {
                  sp >>>= 0;
                  const id = this.mem.getInt32(sp + 8, true);
                  clearTimeout(this._scheduledTimeouts.get(id));
                  this._scheduledTimeouts.delete(id);
                },
                // func getRandomData(r []byte)
                "runtime.getRandomData": (sp) => {
                  sp >>>= 0;
                  crypto.getRandomValues(loadSlice(sp + 8));
                },
                // func finalizeRef(v ref)
                "syscall/js.finalizeRef": (sp) => {
                  sp >>>= 0;
                  const id = this.mem.getUint32(sp + 8, true);
                  this._goRefCounts[id]--;
                  if (this._goRefCounts[id] === 0) {
                    const v = this._values[id];
                    this._values[id] = null;
                    this._ids.delete(v);
                    this._idPool.push(id);
                  }
                },
                // func stringVal(value string) ref
                "syscall/js.stringVal": (sp) => {
                  sp >>>= 0;
                  storeValue(sp + 24, loadString(sp + 8));
                },
                // func valueGet(v ref, p string) ref
                "syscall/js.valueGet": (sp) => {
                  sp >>>= 0;
                  const result = Reflect.get(loadValue(sp + 8), loadString(sp + 16));
                  sp = this._inst.exports.getsp() >>> 0;
                  storeValue(sp + 32, result);
                },
                // func valueSet(v ref, p string, x ref)
                "syscall/js.valueSet": (sp) => {
                  sp >>>= 0;
                  Reflect.set(loadValue(sp + 8), loadString(sp + 16), loadValue(sp + 32));
                },
                // func valueDelete(v ref, p string)
                "syscall/js.valueDelete": (sp) => {
                  sp >>>= 0;
                  Reflect.deleteProperty(loadValue(sp + 8), loadString(sp + 16));
                },
                // func valueIndex(v ref, i int) ref
                "syscall/js.valueIndex": (sp) => {
                  sp >>>= 0;
                  storeValue(sp + 24, Reflect.get(loadValue(sp + 8), getInt64(sp + 16)));
                },
                // valueSetIndex(v ref, i int, x ref)
                "syscall/js.valueSetIndex": (sp) => {
                  sp >>>= 0;
                  Reflect.set(loadValue(sp + 8), getInt64(sp + 16), loadValue(sp + 24));
                },
                // func valueCall(v ref, m string, args []ref) (ref, bool)
                "syscall/js.valueCall": (sp) => {
                  sp >>>= 0;
                  try {
                    const v = loadValue(sp + 8);
                    const m = Reflect.get(v, loadString(sp + 16));
                    const args = loadSliceOfValues(sp + 32);
                    const result = Reflect.apply(m, v, args);
                    sp = this._inst.exports.getsp() >>> 0;
                    storeValue(sp + 56, result);
                    this.mem.setUint8(sp + 64, 1);
                  } catch (err) {
                    sp = this._inst.exports.getsp() >>> 0;
                    storeValue(sp + 56, err);
                    this.mem.setUint8(sp + 64, 0);
                  }
                },
                // func valueInvoke(v ref, args []ref) (ref, bool)
                "syscall/js.valueInvoke": (sp) => {
                  sp >>>= 0;
                  try {
                    const v = loadValue(sp + 8);
                    const args = loadSliceOfValues(sp + 16);
                    const result = Reflect.apply(v, void 0, args);
                    sp = this._inst.exports.getsp() >>> 0;
                    storeValue(sp + 40, result);
                    this.mem.setUint8(sp + 48, 1);
                  } catch (err) {
                    sp = this._inst.exports.getsp() >>> 0;
                    storeValue(sp + 40, err);
                    this.mem.setUint8(sp + 48, 0);
                  }
                },
                // func valueNew(v ref, args []ref) (ref, bool)
                "syscall/js.valueNew": (sp) => {
                  sp >>>= 0;
                  try {
                    const v = loadValue(sp + 8);
                    const args = loadSliceOfValues(sp + 16);
                    const result = Reflect.construct(v, args);
                    sp = this._inst.exports.getsp() >>> 0;
                    storeValue(sp + 40, result);
                    this.mem.setUint8(sp + 48, 1);
                  } catch (err) {
                    sp = this._inst.exports.getsp() >>> 0;
                    storeValue(sp + 40, err);
                    this.mem.setUint8(sp + 48, 0);
                  }
                },
                // func valueLength(v ref) int
                "syscall/js.valueLength": (sp) => {
                  sp >>>= 0;
                  setInt64(sp + 16, parseInt(loadValue(sp + 8).length));
                },
                // valuePrepareString(v ref) (ref, int)
                "syscall/js.valuePrepareString": (sp) => {
                  sp >>>= 0;
                  const str = encoder.encode(String(loadValue(sp + 8)));
                  storeValue(sp + 16, str);
                  setInt64(sp + 24, str.length);
                },
                // valueLoadString(v ref, b []byte)
                "syscall/js.valueLoadString": (sp) => {
                  sp >>>= 0;
                  const str = loadValue(sp + 8);
                  loadSlice(sp + 16).set(str);
                },
                // func valueInstanceOf(v ref, t ref) bool
                "syscall/js.valueInstanceOf": (sp) => {
                  sp >>>= 0;
                  this.mem.setUint8(sp + 24, loadValue(sp + 8) instanceof loadValue(sp + 16) ? 1 : 0);
                },
                // func copyBytesToGo(dst []byte, src ref) (int, bool)
                "syscall/js.copyBytesToGo": (sp) => {
                  sp >>>= 0;
                  const dst = loadSlice(sp + 8);
                  const src = loadValue(sp + 32);
                  if (!(src instanceof Uint8Array || src instanceof Uint8ClampedArray)) {
                    this.mem.setUint8(sp + 48, 0);
                    return;
                  }
                  const toCopy = src.subarray(0, dst.length);
                  dst.set(toCopy);
                  setInt64(sp + 40, toCopy.length);
                  this.mem.setUint8(sp + 48, 1);
                },
                // func copyBytesToJS(dst ref, src []byte) (int, bool)
                "syscall/js.copyBytesToJS": (sp) => {
                  sp >>>= 0;
                  const dst = loadValue(sp + 8);
                  const src = loadSlice(sp + 16);
                  if (!(dst instanceof Uint8Array || dst instanceof Uint8ClampedArray)) {
                    this.mem.setUint8(sp + 48, 0);
                    return;
                  }
                  const toCopy = src.subarray(0, dst.length);
                  dst.set(toCopy);
                  setInt64(sp + 40, toCopy.length);
                  this.mem.setUint8(sp + 48, 1);
                },
                "debug": (value) => {
                  console.log(value);
                }
              }
            };
          }
          run(instance) {
            return __async(this, null, function* () {
              if (!(instance instanceof WebAssembly.Instance)) {
                throw new Error("Go.run: WebAssembly.Instance expected");
              }
              this._inst = instance;
              this.mem = new DataView(this._inst.exports.mem.buffer);
              this._values = [
                // JS values that Go currently has references to, indexed by reference id
                NaN,
                0,
                null,
                true,
                false,
                globalThis,
                this
              ];
              this._goRefCounts = new Array(this._values.length).fill(Infinity);
              this._ids = /* @__PURE__ */ new Map([
                // mapping from JS values to reference ids
                [0, 1],
                [null, 2],
                [true, 3],
                [false, 4],
                [globalThis, 5],
                [this, 6]
              ]);
              this._idPool = [];
              this.exited = false;
              let offset = 4096;
              const strPtr = (str) => {
                const ptr = offset;
                const bytes = encoder.encode(str + "\\0");
                new Uint8Array(this.mem.buffer, offset, bytes.length).set(bytes);
                offset += bytes.length;
                if (offset % 8 !== 0) {
                  offset += 8 - offset % 8;
                }
                return ptr;
              };
              const argc = this.argv.length;
              const argvPtrs = [];
              this.argv.forEach((arg) => {
                argvPtrs.push(strPtr(arg));
              });
              argvPtrs.push(0);
              const keys = Object.keys(this.env).sort();
              keys.forEach((key) => {
                argvPtrs.push(strPtr(\`\${key}=\${this.env[key]}\`));
              });
              argvPtrs.push(0);
              const argv = offset;
              argvPtrs.forEach((ptr) => {
                this.mem.setUint32(offset, ptr, true);
                this.mem.setUint32(offset + 4, 0, true);
                offset += 8;
              });
              const wasmMinDataAddr = 4096 + 8192;
              if (offset >= wasmMinDataAddr) {
                throw new Error("total length of command line and environment variables exceeds limit");
              }
              this._inst.exports.run(argc, argv);
              if (this.exited) {
                this._resolveExitPromise();
              }
              yield this._exitPromise;
            });
          }
          _resume() {
            if (this.exited) {
              throw new Error("Go program has already exited");
            }
            this._inst.exports.resume();
            if (this.exited) {
              this._resolveExitPromise();
            }
          }
          _makeFuncWrapper(id) {
            const go = this;
            return function() {
              const event = { id, this: this, args: arguments };
              go._pendingEvent = event;
              go._resume();
              return event.result;
            };
          }
        };
      })();
      onmessage = ({ data: wasm }) => {
        let decoder = new TextDecoder();
        let fs = globalThis.fs;
        let stderr = "";
        fs.writeSync = (fd, buffer) => {
          if (fd === 1) {
            postMessage(buffer);
          } else if (fd === 2) {
            stderr += decoder.decode(buffer);
            let parts = stderr.split("\\n");
            if (parts.length > 1) console.log(parts.slice(0, -1).join("\\n"));
            stderr = parts[parts.length - 1];
          } else {
            throw new Error("Bad write");
          }
          return buffer.length;
        };
        let stdin = [];
        let resumeStdin;
        let stdinPos = 0;
        onmessage = ({ data }) => {
          if (data.length > 0) {
            stdin.push(data);
            if (resumeStdin) resumeStdin();
          }
          return go;
        };
        fs.read = (fd, buffer, offset, length, position, callback) => {
          if (fd !== 0 || offset !== 0 || length !== buffer.length || position !== null) {
            throw new Error("Bad read");
          }
          if (stdin.length === 0) {
            resumeStdin = () => fs.read(fd, buffer, offset, length, position, callback);
            return;
          }
          let first = stdin[0];
          let count = Math.max(0, Math.min(length, first.length - stdinPos));
          buffer.set(first.subarray(stdinPos, stdinPos + count), offset);
          stdinPos += count;
          if (stdinPos === first.length) {
            stdin.shift();
            stdinPos = 0;
          }
          callback(null, count);
        };
        let go = new globalThis.Go();
        go.argv = ["", \`--service=\${"0.24.2"}\`];
        tryToInstantiateModule(wasm, go).then(
          (instance) => {
            postMessage(null);
            go.run(instance);
          },
          (error) => {
            postMessage(error);
          }
        );
        return go;
      };
      function tryToInstantiateModule(wasm, go) {
        return __async(this, null, function* () {
          if (wasm instanceof WebAssembly.Module) {
            return WebAssembly.instantiate(wasm, go.importObject);
          }
          const res = yield fetch(wasm);
          if (!res.ok) throw new Error(\`Failed to download \${JSON.stringify(wasm)}\`);
          if ("instantiateStreaming" in WebAssembly && /^application\\/wasm($|;)/i.test(res.headers.get("Content-Type") || "")) {
            const result2 = yield WebAssembly.instantiateStreaming(res, go.importObject);
            return result2.instance;
          }
          const bytes = yield res.arrayBuffer();
          const result = yield WebAssembly.instantiate(bytes, go.importObject);
          return result.instance;
        });
      }
      return (m) => onmessage(m);
    })(postMessage)`],{type:"text/javascript"});a=new Worker(URL.createObjectURL(e))}else{let e,t=(e=>{let t;var r=(e,t,r)=>new Promise((n,i)=>{var s=e=>{try{l(r.next(e))}catch(e){i(e)}},o=e=>{try{l(r.throw(e))}catch(e){i(e)}},l=e=>e.done?n(e.value):Promise.resolve(e.value).then(s,o);l((r=r.apply(e,t)).next())});let n={};for(let e=self;e;e=Object.getPrototypeOf(e))for(let t of Object.getOwnPropertyNames(e))t in n||Object.defineProperty(n,t,{get:()=>self[t]});let i=()=>{let e=Error("not implemented");return e.code="ENOSYS",e};if(!n.fs){let e="";n.fs={constants:{O_WRONLY:-1,O_RDWR:-1,O_CREAT:-1,O_TRUNC:-1,O_APPEND:-1,O_EXCL:-1},writeSync(t,r){let n=(e+=o.decode(r)).lastIndexOf("\n");return -1!=n&&(console.log(e.substring(0,n)),e=e.substring(n+1)),r.length},write(e,t,r,n,s,o){0!==r||n!==t.length||null!==s?o(i()):o(null,this.writeSync(e,t))},chmod(e,t,r){r(i())},chown(e,t,r,n){n(i())},close(e,t){t(i())},fchmod(e,t,r){r(i())},fchown(e,t,r,n){n(i())},fstat(e,t){t(i())},fsync(e,t){t(null)},ftruncate(e,t,r){r(i())},lchown(e,t,r,n){n(i())},link(e,t,r){r(i())},lstat(e,t){t(i())},mkdir(e,t,r){r(i())},open(e,t,r,n){n(i())},read(e,t,r,n,s,o){o(i())},readdir(e,t){t(i())},readlink(e,t){t(i())},rename(e,t,r){r(i())},rmdir(e,t){t(i())},stat(e,t){t(i())},symlink(e,t,r){r(i())},truncate(e,t,r){r(i())},unlink(e,t){t(i())},utimes(e,t,r,n){n(i())}}}if(n.process||(n.process={getuid:()=>-1,getgid:()=>-1,geteuid:()=>-1,getegid:()=>-1,getgroups(){throw i()},pid:-1,ppid:-1,umask(){throw i()},cwd(){throw i()},chdir(){throw i()}}),!n.crypto)throw Error("globalThis.crypto is not available, polyfill required (crypto.getRandomValues only)");if(!n.performance)throw Error("globalThis.performance is not available, polyfill required (performance.now only)");if(!n.TextEncoder)throw Error("globalThis.TextEncoder is not available, polyfill required");if(!n.TextDecoder)throw Error("globalThis.TextDecoder is not available, polyfill required");let s=new TextEncoder("utf-8"),o=new TextDecoder("utf-8");return n.Go=class{constructor(){this.argv=["js"],this.env={},this.exit=e=>{0!==e&&console.warn("exit code:",e)},this._exitPromise=new Promise(e=>{this._resolveExitPromise=e}),this._pendingEvent=null,this._scheduledTimeouts=new Map,this._nextCallbackTimeoutID=1;const e=(e,t)=>{this.mem.setUint32(e+0,t,!0),this.mem.setUint32(e+4,Math.floor(t/0x100000000),!0)},t=e=>this.mem.getUint32(e+0,!0)+0x100000000*this.mem.getInt32(e+4,!0),r=e=>{let t=this.mem.getFloat64(e,!0);if(0===t)return;if(!isNaN(t))return t;let r=this.mem.getUint32(e,!0);return this._values[r]},i=(e,t)=>{if("number"==typeof t&&0!==t){if(isNaN(t)){this.mem.setUint32(e+4,0x7ff80000,!0),this.mem.setUint32(e,0,!0);return}this.mem.setFloat64(e,t,!0);return}if(void 0===t)return void this.mem.setFloat64(e,0,!0);let r=this._ids.get(t);void 0===r&&(void 0===(r=this._idPool.pop())&&(r=this._values.length),this._values[r]=t,this._goRefCounts[r]=0,this._ids.set(t,r)),this._goRefCounts[r]++;let n=0;switch(typeof t){case"object":null!==t&&(n=1);break;case"string":n=2;break;case"symbol":n=3;break;case"function":n=4}this.mem.setUint32(e+4,0x7ff80000|n,!0),this.mem.setUint32(e,r,!0)},l=e=>{let r=t(e+0),n=t(e+8);return new Uint8Array(this._inst.exports.mem.buffer,r,n)},a=e=>{let n=t(e+0),i=t(e+8),s=Array(i);for(let e=0;e<i;e++)s[e]=r(n+8*e);return s},u=e=>{let r=t(e+0),n=t(e+8);return o.decode(new DataView(this._inst.exports.mem.buffer,r,n))},c=Date.now()-performance.now();this.importObject={_gotest:{add:(e,t)=>e+t},gojs:{"runtime.wasmExit":e=>{e>>>=0;let t=this.mem.getInt32(e+8,!0);this.exited=!0,delete this._inst,delete this._values,delete this._goRefCounts,delete this._ids,delete this._idPool,this.exit(t)},"runtime.wasmWrite":e=>{let r=t((e>>>=0)+8),i=t(e+16),s=this.mem.getInt32(e+24,!0);n.fs.writeSync(r,new Uint8Array(this._inst.exports.mem.buffer,i,s))},"runtime.resetMemoryDataView":e=>{this.mem=new DataView(this._inst.exports.mem.buffer)},"runtime.nanotime1":t=>{e((t>>>=0)+8,(c+performance.now())*1e6)},"runtime.walltime":t=>{t>>>=0;let r=new Date().getTime();e(t+8,r/1e3),this.mem.setInt32(t+16,r%1e3*1e6,!0)},"runtime.scheduleTimeoutEvent":e=>{e>>>=0;let r=this._nextCallbackTimeoutID;this._nextCallbackTimeoutID++,this._scheduledTimeouts.set(r,setTimeout(()=>{for(this._resume();this._scheduledTimeouts.has(r);)console.warn("scheduleTimeoutEvent: missed timeout event"),this._resume()},t(e+8))),this.mem.setInt32(e+16,r,!0)},"runtime.clearTimeoutEvent":e=>{e>>>=0;let t=this.mem.getInt32(e+8,!0);clearTimeout(this._scheduledTimeouts.get(t)),this._scheduledTimeouts.delete(t)},"runtime.getRandomData":e=>{e>>>=0,crypto.getRandomValues(l(e+8))},"syscall/js.finalizeRef":e=>{e>>>=0;let t=this.mem.getUint32(e+8,!0);if(this._goRefCounts[t]--,0===this._goRefCounts[t]){let e=this._values[t];this._values[t]=null,this._ids.delete(e),this._idPool.push(t)}},"syscall/js.stringVal":e=>{i((e>>>=0)+24,u(e+8))},"syscall/js.valueGet":e=>{let t=Reflect.get(r((e>>>=0)+8),u(e+16));i((e=this._inst.exports.getsp()>>>0)+32,t)},"syscall/js.valueSet":e=>{Reflect.set(r((e>>>=0)+8),u(e+16),r(e+32))},"syscall/js.valueDelete":e=>{Reflect.deleteProperty(r((e>>>=0)+8),u(e+16))},"syscall/js.valueIndex":e=>{i((e>>>=0)+24,Reflect.get(r(e+8),t(e+16)))},"syscall/js.valueSetIndex":e=>{Reflect.set(r((e>>>=0)+8),t(e+16),r(e+24))},"syscall/js.valueCall":e=>{e>>>=0;try{let t=r(e+8),n=Reflect.get(t,u(e+16)),s=a(e+32),o=Reflect.apply(n,t,s);e=this._inst.exports.getsp()>>>0,i(e+56,o),this.mem.setUint8(e+64,1)}catch(t){i((e=this._inst.exports.getsp()>>>0)+56,t),this.mem.setUint8(e+64,0)}},"syscall/js.valueInvoke":e=>{e>>>=0;try{let t=r(e+8),n=a(e+16),s=Reflect.apply(t,void 0,n);e=this._inst.exports.getsp()>>>0,i(e+40,s),this.mem.setUint8(e+48,1)}catch(t){i((e=this._inst.exports.getsp()>>>0)+40,t),this.mem.setUint8(e+48,0)}},"syscall/js.valueNew":e=>{e>>>=0;try{let t=r(e+8),n=a(e+16),s=Reflect.construct(t,n);e=this._inst.exports.getsp()>>>0,i(e+40,s),this.mem.setUint8(e+48,1)}catch(t){i((e=this._inst.exports.getsp()>>>0)+40,t),this.mem.setUint8(e+48,0)}},"syscall/js.valueLength":t=>{e((t>>>=0)+16,parseInt(r(t+8).length))},"syscall/js.valuePrepareString":t=>{t>>>=0;let n=s.encode(String(r(t+8)));i(t+16,n),e(t+24,n.length)},"syscall/js.valueLoadString":e=>{let t=r((e>>>=0)+8);l(e+16).set(t)},"syscall/js.valueInstanceOf":e=>{e>>>=0,this.mem.setUint8(e+24,+(r(e+8)instanceof r(e+16)))},"syscall/js.copyBytesToGo":t=>{let n=l((t>>>=0)+8),i=r(t+32);if(!(i instanceof Uint8Array||i instanceof Uint8ClampedArray))return void this.mem.setUint8(t+48,0);let s=i.subarray(0,n.length);n.set(s),e(t+40,s.length),this.mem.setUint8(t+48,1)},"syscall/js.copyBytesToJS":t=>{let n=r((t>>>=0)+8),i=l(t+16);if(!(n instanceof Uint8Array||n instanceof Uint8ClampedArray))return void this.mem.setUint8(t+48,0);let s=i.subarray(0,n.length);n.set(s),e(t+40,s.length),this.mem.setUint8(t+48,1)},debug:e=>{console.log(e)}}}}run(e){return r(this,null,function*(){if(!(e instanceof WebAssembly.Instance))throw Error("Go.run: WebAssembly.Instance expected");this._inst=e,this.mem=new DataView(this._inst.exports.mem.buffer),this._values=[NaN,0,null,!0,!1,n,this],this._goRefCounts=Array(this._values.length).fill(1/0),this._ids=new Map([[0,1],[null,2],[!0,3],[!1,4],[n,5],[this,6]]),this._idPool=[],this.exited=!1;let t=4096,r=e=>{let r=t,n=s.encode(e+"\0");return new Uint8Array(this.mem.buffer,t,n.length).set(n),(t+=n.length)%8!=0&&(t+=8-t%8),r},i=this.argv.length,o=[];this.argv.forEach(e=>{o.push(r(e))}),o.push(0),Object.keys(this.env).sort().forEach(e=>{o.push(r(`${e}=${this.env[e]}`))}),o.push(0);let l=t;if(o.forEach(e=>{this.mem.setUint32(t,e,!0),this.mem.setUint32(t+4,0,!0),t+=8}),t>=12288)throw Error("total length of command line and environment variables exceeds limit");this._inst.exports.run(i,l),this.exited&&this._resolveExitPromise(),yield this._exitPromise})}_resume(){if(this.exited)throw Error("Go program has already exited");this._inst.exports.resume(),this.exited&&this._resolveExitPromise()}_makeFuncWrapper(e){let t=this;return function(){let r={id:e,this:this,args:arguments};return t._pendingEvent=r,t._resume(),r.result}}},t=({data:i})=>{let s,o=new TextDecoder,l=n.fs,a="";l.writeSync=(t,r)=>{if(1===t)e(r);else if(2===t){let e=(a+=o.decode(r)).split("\n");e.length>1&&console.log(e.slice(0,-1).join("\n")),a=e[e.length-1]}else throw Error("Bad write");return r.length};let u=[],c=0;t=({data:e})=>(e.length>0&&(u.push(e),s&&s()),f),l.read=(e,t,r,n,i,o)=>{if(0!==e||0!==r||n!==t.length||null!==i)throw Error("Bad read");if(0===u.length){s=()=>l.read(e,t,r,n,i,o);return}let a=u[0],f=Math.max(0,Math.min(n,a.length-c));t.set(a.subarray(c,c+f),r),(c+=f)===a.length&&(u.shift(),c=0),o(null,f)};let f=new n.Go;return f.argv=["","--service=0.24.2"],(function(e,t){return r(this,null,function*(){if(e instanceof WebAssembly.Module)return WebAssembly.instantiate(e,t.importObject);let r=yield fetch(e);if(!r.ok)throw Error(`Failed to download ${JSON.stringify(e)}`);if("instantiateStreaming"in WebAssembly&&/^application\/wasm($|;)/i.test(r.headers.get("Content-Type")||""))return(yield WebAssembly.instantiateStreaming(r,t.importObject)).instance;let n=yield r.arrayBuffer();return(yield WebAssembly.instantiate(n,t.importObject)).instance})})(i,f).then(t=>{e(null),f.run(t)},t=>{e(t)}),f},e=>t(e)})(e=>a.onmessage({data:e}));a={onmessage:null,postMessage:r=>setTimeout(()=>{try{e=t({data:r})}catch(e){u(e)}}),terminate(){if(e)for(let t of e._scheduledTimeouts.values())clearTimeout(t)}}}let m=new Promise((e,t)=>{c=e,f=t});a.onmessage=({data:e})=>{a.onmessage=({data:e})=>b(e),e?f(e):c()},a.postMessage(n||new URL(e,location.href).toString());let{readFromStdout:b,service:j}=function(e){let n={},i={didClose:!1,reason:""},s={},o=0,l=0,a=new Uint8Array(16384),u=0,c=(t,r,n)=>{if(i.didClose)return n("The service is no longer running"+i.reason,null);let l=o++;s[l]=(e,r)=>{try{n(e,r)}finally{t&&t.unref()}},t&&t.ref(),e.writeToStdin(g({id:l,isRequest:!0,value:r}))},f=(t,r)=>{if(i.didClose)throw Error("The service is no longer running"+i.reason);e.writeToStdin(g({id:t,isRequest:!1,value:r}))},h=(t,r)=>d(this,null,function*(){try{if("ping"===r.command)return void f(t,{});if("number"==typeof r.key){let e=n[r.key];if(!e)return;let i=e[r.command];if(i)return void(yield i(t,r))}throw Error("Invalid command: "+r.command)}catch(n){let r=[H(n,e,null,void 0,"")];try{f(t,{errors:r})}catch(e){}}}),p=!0,m=e=>{if(p){p=!1;let t=String.fromCharCode(...e);if("0.24.2"!==t)throw Error(`Cannot start service: Host version "0.24.2" does not match binary version ${w(t)}`);return}let t=function(e){let t=()=>{switch(n.read8()){case 0:return null;case 1:return!!n.read8();case 2:return n.read32();case 3:return r(n.read());case 4:return n.read();case 5:{let e=n.read32(),r=[];for(let n=0;n<e;n++)r.push(t());return r}case 6:{let e=n.read32(),i={};for(let s=0;s<e;s++)i[r(n.read())]=t();return i}default:throw Error("Invalid packet")}},n=new y(e),i=n.read32(),s=(1&i)==0;i>>>=1;let o=t();if(n.ptr!==e.length)throw Error("Invalid packet");return{id:i,isRequest:s,value:o}}(e);if(t.isRequest)h(t.id,t.value);else{let e=s[t.id];delete s[t.id],t.value.error?e(t.value.error,{}):e(null,t.value)}};return{readFromStdout:e=>{let t=u+e.length;if(t>a.length){let e=new Uint8Array(2*t);e.set(a),a=e}a.set(e,u),u+=e.length;let r=0;for(;r+4<=u;){let e=v(a,r);if(r+4+e>u)break;r+=4,m(a.subarray(r,r+e)),r+=e}r>0&&(a.copyWithin(0,r,u),u-=r)},afterClose:e=>{i.didClose=!0,e&&(i.reason=": "+(e.message||e));let t="The service was stopped"+i.reason;for(let e in s)s[e](t,null);s={}},service:{buildOrContext:({callName:i,refs:s,options:o,isTTY:a,defaultWD:u,callback:h})=>{let p=0,m=l++,g={},y={ref(){1==++p&&s&&s.ref()},unref(){0==--p&&(delete n[m],s&&s.unref())}};n[m]=g,y.ref(),function(e,n,i,s,o,l,a,u,c,f,h){let p,m=G(),g="context"===e,y=(e,t)=>{let r=[];try{B(r,u,{},c,x)}catch(e){}let n=H(e,l,m,void 0,t);i(o,{command:"error",flags:r,error:n},()=>{n.detail=m.load(n.detail),h(K(g?"Context failed":"Build failed",[n],[]),null)})};if("object"==typeof u){let e=u.plugins;if(void 0!==e){if(!Array.isArray(e))return y(Error('"plugins" must be an array'),"");p=e}}if(p&&p.length>0){let e,r,c,f,h,g,b,x,E;return l.isSync?y(Error("Cannot use plugins in synchronous API calls"),""):(e=n,r=i,c=s,f=o,h=l,g=a,b=u,x=p,E=m,d(void 0,null,function*(){let n=[],i=[],s={},o={},l=[],a=0,u=0,p=[],m=!1;for(let t of x=[...x]){let c={};if("object"!=typeof t)throw Error(`Plugin at index ${u} must be an object`);let d=V(t,c,"name",_);if("string"!=typeof d||""===d)throw Error(`Plugin at index ${u} is missing a name`);try{let g=V(t,c,"setup",S);if("function"!=typeof g)throw Error("Plugin is missing a setup function");L(t,c,`on plugin ${w(d)}`);let y={name:d,onStart:!1,onEnd:!1,onResolve:[],onLoad:[]};u++;let v=(t,n={})=>{if(!m)throw Error('Cannot call "resolve" before plugin setup has completed');if("string"!=typeof t)throw Error("The path to resolve must be a string");let i=Object.create(null),s=V(n,i,"pluginName",_),o=V(n,i,"importer",_),l=V(n,i,"namespace",_),a=V(n,i,"resolveDir",_),u=V(n,i,"kind",_),c=V(n,i,"pluginData",k),h=V(n,i,"with",R);return L(n,i,"in resolve() call"),new Promise((n,i)=>{let p={command:"resolve",path:t,key:e,pluginName:d};if(null!=s&&(p.pluginName=s),null!=o&&(p.importer=o),null!=l&&(p.namespace=l),null!=a&&(p.resolveDir=a),null!=u)p.kind=u;else throw Error('Must specify "kind" when calling "resolve"');null!=c&&(p.pluginData=E.store(c)),null!=h&&(p.with=function(e,t){let r=Object.create(null);for(let n in e){let i=e[n];if("string"!=typeof i)throw Error(`key ${w(n)} in object ${w(t)} must be a string`);r[n]=i}return r}(h,"with")),r(f,p,(e,t)=>{null!==e?i(Error(e)):n({errors:X(t.errors,E),warnings:X(t.warnings,E),path:t.path,external:t.external,sideEffects:t.sideEffects,namespace:t.namespace,suffix:t.suffix,pluginData:E.load(t.pluginData)})})})},x=g({initialOptions:b,resolve:v,onStart(e){let t=Y(Error('This error came from the "onStart" callback registered here:'),h,"onStart");n.push({name:d,callback:e,note:t}),y.onStart=!0},onEnd(e){let t=Y(Error('This error came from the "onEnd" callback registered here:'),h,"onEnd");i.push({name:d,callback:e,note:t}),y.onEnd=!0},onResolve(e,t){let r=Y(Error('This error came from the "onResolve" callback registered here:'),h,"onResolve"),n={},i=V(e,n,"filter",T),o=V(e,n,"namespace",_);if(L(e,n,`in onResolve() call for plugin ${w(d)}`),null==i)throw Error("onResolve() call is missing a filter");let l=a++;s[l]={name:d,callback:t,note:r},y.onResolve.push({id:l,filter:i.source,namespace:o||""})},onLoad(e,t){let r=Y(Error('This error came from the "onLoad" callback registered here:'),h,"onLoad"),n={},i=V(e,n,"filter",T),s=V(e,n,"namespace",_);if(L(e,n,`in onLoad() call for plugin ${w(d)}`),null==i)throw Error("onLoad() call is missing a filter");let l=a++;o[l]={name:d,callback:t,note:r},y.onLoad.push({id:l,filter:i.source,namespace:s||""})},onDispose(e){l.push(e)},esbuild:h.esbuild});x&&(yield x),p.push(y)}catch(e){return{ok:!1,error:e,pluginName:d}}}g["on-start"]=(e,t)=>d(void 0,null,function*(){E.clear();let t={errors:[],warnings:[]};yield Promise.all(n.map(e=>d(void 0,[e],function*({name:e,callback:r,note:n}){try{let n=yield r();if(null!=n){if("object"!=typeof n)throw Error(`Expected onStart() callback in plugin ${w(e)} to return an object`);let r={},i=V(n,r,"errors",P),s=V(n,r,"warnings",P);L(n,r,`from onStart() callback in plugin ${w(e)}`),null!=i&&t.errors.push(...Z(i,"errors",E,e,void 0)),null!=s&&t.warnings.push(...Z(s,"warnings",E,e,void 0))}}catch(r){t.errors.push(H(r,h,E,n&&n(),e))}}))),c(e,t)}),g["on-resolve"]=(e,t)=>d(void 0,null,function*(){let r={},n="",i,o;for(let e of t.ids)try{({name:n,callback:i,note:o}=s[e]);let l=yield i({path:t.path,importer:t.importer,namespace:t.namespace,resolveDir:t.resolveDir,kind:t.kind,pluginData:E.load(t.pluginData),with:t.with});if(null!=l){if("object"!=typeof l)throw Error(`Expected onResolve() callback in plugin ${w(n)} to return an object`);let t={},i=V(l,t,"pluginName",_),s=V(l,t,"path",_),o=V(l,t,"namespace",_),a=V(l,t,"suffix",_),u=V(l,t,"external",O),c=V(l,t,"sideEffects",O),f=V(l,t,"pluginData",k),d=V(l,t,"errors",P),h=V(l,t,"warnings",P),p=V(l,t,"watchFiles",P),m=V(l,t,"watchDirs",P);L(l,t,`from onResolve() callback in plugin ${w(n)}`),r.id=e,null!=i&&(r.pluginName=i),null!=s&&(r.path=s),null!=o&&(r.namespace=o),null!=a&&(r.suffix=a),null!=u&&(r.external=u),null!=c&&(r.sideEffects=c),null!=f&&(r.pluginData=E.store(f)),null!=d&&(r.errors=Z(d,"errors",E,n,void 0)),null!=h&&(r.warnings=Z(h,"warnings",E,n,void 0)),null!=p&&(r.watchFiles=ee(p,"watchFiles")),null!=m&&(r.watchDirs=ee(m,"watchDirs"));break}}catch(t){r={id:e,errors:[H(t,h,E,o&&o(),n)]};break}c(e,r)}),g["on-load"]=(e,r)=>d(void 0,null,function*(){let n={},i="",s,l;for(let e of r.ids)try{({name:i,callback:s,note:l}=o[e]);let a=yield s({path:r.path,namespace:r.namespace,suffix:r.suffix,pluginData:E.load(r.pluginData),with:r.with});if(null!=a){if("object"!=typeof a)throw Error(`Expected onLoad() callback in plugin ${w(i)} to return an object`);let r={},s=V(a,r,"pluginName",_),o=V(a,r,"contents",N),l=V(a,r,"resolveDir",_),u=V(a,r,"pluginData",k),c=V(a,r,"loader",_),f=V(a,r,"errors",P),d=V(a,r,"warnings",P),h=V(a,r,"watchFiles",P),p=V(a,r,"watchDirs",P);L(a,r,`from onLoad() callback in plugin ${w(i)}`),n.id=e,null!=s&&(n.pluginName=s),o instanceof Uint8Array?n.contents=o:null!=o&&(n.contents=t(o)),null!=l&&(n.resolveDir=l),null!=u&&(n.pluginData=E.store(u)),null!=c&&(n.loader=c),null!=f&&(n.errors=Z(f,"errors",E,i,void 0)),null!=d&&(n.warnings=Z(d,"warnings",E,i,void 0)),null!=h&&(n.watchFiles=ee(h,"watchFiles")),null!=p&&(n.watchDirs=ee(p,"watchDirs"));break}}catch(t){n={id:e,errors:[H(t,h,E,l&&l(),i)]};break}c(e,n)});let y=(e,t)=>t([],[]);return i.length>0&&(y=(e,t)=>{d(void 0,null,function*(){let r=[],n=[];for(let{name:t,callback:s,note:o}of i){let i,l;try{let r=yield s(e);if(null!=r){if("object"!=typeof r)throw Error(`Expected onEnd() callback in plugin ${w(t)} to return an object`);let e={},n=V(r,e,"errors",P),s=V(r,e,"warnings",P);L(r,e,`from onEnd() callback in plugin ${w(t)}`),null!=n&&(i=Z(n,"errors",E,t,void 0)),null!=s&&(l=Z(s,"warnings",E,t,void 0))}}catch(e){i=[H(e,h,E,o&&o(),t)]}if(i){r.push(...i);try{e.errors.push(...i)}catch(e){}}if(l){n.push(...l);try{e.warnings.push(...l)}catch(e){}}}t(r,n)})}),m=!0,{ok:!0,requestPlugins:p,runOnEndCallbacks:y,scheduleOnDisposeCallbacks:()=>{for(let e of l)setTimeout(()=>e(),0)}}})).then(e=>{if(!e.ok)return y(e.error,e.pluginName);try{v(e.requestPlugins,e.runOnEndCallbacks,e.scheduleOnDisposeCallbacks)}catch(e){y(e,"")}},e=>y(e,""))}try{v(null,(e,t)=>t([],[]),()=>{})}catch(e){y(e,"")}function v(d,p,y){let v,b,{entries:w,flags:E,write:j,stdinContents:k,stdinResolveDir:T,absWorkingDir:M,nodePaths:I,mangleCache:A}=function(e,r,n,i,s){var o;let l=[],a=[],u=Object.create(null),c=null,f=null;B(l,r,u,n,i),q(l,r,u);let d=V(r,u,"sourcemap",U),h=V(r,u,"bundle",O),p=V(r,u,"splitting",O),m=V(r,u,"preserveSymlinks",O),g=V(r,u,"metafile",O),y=V(r,u,"outfile",_),v=V(r,u,"outdir",_),b=V(r,u,"outbase",_),w=V(r,u,"tsconfig",_),x=V(r,u,"resolveExtensions",P),E=V(r,u,"nodePaths",P),j=V(r,u,"mainFields",P),k=V(r,u,"conditions",P),T=V(r,u,"external",P),$=V(r,u,"packages",_),S=V(r,u,"alias",R),M=V(r,u,"loader",R),I=V(r,u,"outExtension",R),A=V(r,u,"publicPath",_),D=V(r,u,"entryNames",_),F=V(r,u,"chunkNames",_),G=V(r,u,"assetNames",_),Y=V(r,u,"inject",P),H=V(r,u,"banner",R),J=V(r,u,"footer",R),K=V(r,u,"entryPoints",C),X=V(r,u,"absWorkingDir",_),Q=V(r,u,"stdin",R),Z=null!=(o=V(r,u,"write",O))?o:s,ee=V(r,u,"allowOverwrite",O),et=V(r,u,"mangleCache",R);if(u.plugins=!0,L(r,u,`in ${e}() call`),d&&l.push(`--sourcemap${!0===d?"":`=${d}`}`),h&&l.push("--bundle"),ee&&l.push("--allow-overwrite"),p&&l.push("--splitting"),m&&l.push("--preserve-symlinks"),g&&l.push("--metafile"),y&&l.push(`--outfile=${y}`),v&&l.push(`--outdir=${v}`),b&&l.push(`--outbase=${b}`),w&&l.push(`--tsconfig=${w}`),$&&l.push(`--packages=${$}`),x){let e=[];for(let t of x){if(z(t,"resolve extension"),t.indexOf(",")>=0)throw Error(`Invalid resolve extension: ${t}`);e.push(t)}l.push(`--resolve-extensions=${e.join(",")}`)}if(A&&l.push(`--public-path=${A}`),D&&l.push(`--entry-names=${D}`),F&&l.push(`--chunk-names=${F}`),G&&l.push(`--asset-names=${G}`),j){let e=[];for(let t of j){if(z(t,"main field"),t.indexOf(",")>=0)throw Error(`Invalid main field: ${t}`);e.push(t)}l.push(`--main-fields=${e.join(",")}`)}if(k){let e=[];for(let t of k){if(z(t,"condition"),t.indexOf(",")>=0)throw Error(`Invalid condition: ${t}`);e.push(t)}l.push(`--conditions=${e.join(",")}`)}if(T)for(let e of T)l.push(`--external:${z(e,"external")}`);if(S)for(let e in S){if(e.indexOf("=")>=0)throw Error(`Invalid package name in alias: ${e}`);l.push(`--alias:${e}=${z(S[e],"alias",e)}`)}if(H)for(let e in H){if(e.indexOf("=")>=0)throw Error(`Invalid banner file type: ${e}`);l.push(`--banner:${e}=${z(H[e],"banner",e)}`)}if(J)for(let e in J){if(e.indexOf("=")>=0)throw Error(`Invalid footer file type: ${e}`);l.push(`--footer:${e}=${z(J[e],"footer",e)}`)}if(Y)for(let e of Y)l.push(`--inject:${z(e,"inject")}`);if(M)for(let e in M){if(e.indexOf("=")>=0)throw Error(`Invalid loader extension: ${e}`);l.push(`--loader:${e}=${z(M[e],"loader",e)}`)}if(I)for(let e in I){if(e.indexOf("=")>=0)throw Error(`Invalid out extension: ${e}`);l.push(`--out-extension:${e}=${z(I[e],"out extension",e)}`)}if(K)if(Array.isArray(K))for(let e=0,t=K.length;e<t;e++){let t=K[e];if("object"==typeof t&&null!==t){let r=Object.create(null),n=V(t,r,"in",_),i=V(t,r,"out",_);if(L(t,r,"in entry point at index "+e),void 0===n)throw Error('Missing property "in" for entry point at index '+e);if(void 0===i)throw Error('Missing property "out" for entry point at index '+e);a.push([i,n])}else a.push(["",z(t,"entry point at index "+e)])}else for(let e in K)a.push([e,z(K[e],"entry point",e)]);if(Q){let e=Object.create(null),r=V(Q,e,"contents",N),n=V(Q,e,"resolveDir",_),i=V(Q,e,"sourcefile",_),s=V(Q,e,"loader",_);L(Q,e,'in "stdin" object'),i&&l.push(`--sourcefile=${i}`),s&&l.push(`--loader=${s}`),n&&(f=n),"string"==typeof r?c=t(r):r instanceof Uint8Array&&(c=r)}let er=[];if(E)for(let e of E)e+="",er.push(e);return{entries:a,flags:l,write:Z,stdinContents:c,stdinResolveDir:f,absWorkingDir:X,nodePaths:er,mangleCache:W(et)}}(e,u,c,x,l.hasFS);if(j&&!l.hasFS)throw Error('The "write" option is unavailable in this environment');let D={command:"build",key:n,entries:w,flags:E,write:j,stdinContents:k,stdinResolveDir:T,absWorkingDir:M||f,nodePaths:I,context:g};d&&(D.plugins=d),A&&(D.mangleCache=A);let F=(e,t)=>{let n={errors:X(e.errors,m),warnings:X(e.warnings,m),outputFiles:void 0,metafile:void 0,mangleCache:void 0},i=n.errors.slice(),s=n.warnings.slice();e.outputFiles&&(n.outputFiles=e.outputFiles.map(et)),e.metafile&&(n.metafile=JSON.parse(e.metafile)),e.mangleCache&&(n.mangleCache=e.mangleCache),void 0!==e.writeToStdout&&console.log(r(e.writeToStdout).replace(/\n$/,"")),p(n,(e,r)=>{if(i.length>0||e.length>0)return t(K("Build failed",i.concat(e),s.concat(r)),null,e,r);t(null,n,e,r)})};g&&(a["on-end"]=(e,t)=>new Promise(r=>{F(t,(t,n,i,o)=>{b&&b(t,n),v=void 0,b=void 0,s(e,{errors:i,warnings:o}),r()})})),i(o,D,(e,t)=>{if(e)return h(Error(e),null);if(!g)return F(t,(e,t)=>(y(),h(e,t)));if(t.errors.length>0)return h(K("Context failed",t.errors,t.warnings),null);let r=!1;o.ref(),h(null,{rebuild:()=>(v||(v=new Promise((e,t)=>{let r;b=(n,i)=>{r||(r=()=>n?t(n):e(i))};let s=()=>{i(o,{command:"rebuild",key:n},(e,n)=>{e?t(Error(e)):r?r():s()})};s()})),v),watch:(e={})=>new Promise((t,r)=>{if(!l.hasFS)throw Error('Cannot use the "watch" API in this environment');L(e,{},"in watch() call"),i(o,{command:"watch",key:n},e=>{e?r(Error(e)):t(void 0)})}),serve:(e={})=>new Promise((t,r)=>{if(!l.hasFS)throw Error('Cannot use the "serve" API in this environment');let u={},c=V(e,u,"port",$),f=V(e,u,"host",_),d=V(e,u,"servedir",_),h=V(e,u,"keyfile",_),p=V(e,u,"certfile",_),m=V(e,u,"fallback",_),g=V(e,u,"onRequest",S);L(e,u,"in serve() call");let y={command:"serve",key:n,onRequest:!!g};void 0!==c&&(y.port=c),void 0!==f&&(y.host=f),void 0!==d&&(y.servedir=d),void 0!==h&&(y.keyfile=h),void 0!==p&&(y.certfile=p),void 0!==m&&(y.fallback=m),i(o,y,(e,n)=>{if(e)return r(Error(e));g&&(a["serve-request"]=(e,t)=>{g(t.args),s(e,{})}),t(n)})}),cancel:()=>new Promise(e=>{if(r)return e();i(o,{command:"cancel",key:n},()=>{e()})}),dispose:()=>new Promise(e=>{if(r)return e();r=!0,i(o,{command:"dispose",key:n},()=>{e(),y(),o.unref()})})})})}}(i,m,c,f,y,e,g,o,a,u,(e,t)=>{try{h(e,t)}finally{y.unref()}})},transform:({callName:r,refs:n,input:i,options:s,isTTY:o,fs:l,callback:a})=>{let u=G(),f=f=>{try{let e,d,h,p,m,g,y,v;if("string"!=typeof i&&!(i instanceof Uint8Array))throw Error('The input to "transform" must be a string or a Uint8Array');let{flags:b,mangleCache:w}=(e=[],d=Object.create(null),B(e,s,d,o,E),q(e,s,d),h=V(s,d,"sourcemap",U),p=V(s,d,"sourcefile",_),m=V(s,d,"loader",_),g=V(s,d,"banner",_),y=V(s,d,"footer",_),v=V(s,d,"mangleCache",R),L(s,d,`in ${r}() call`),h&&e.push(`--sourcemap=${!0===h?"external":h}`),p&&e.push(`--sourcefile=${p}`),m&&e.push(`--loader=${m}`),g&&e.push(`--banner=${g}`),y&&e.push(`--footer=${y}`),{flags:e,mangleCache:W(v)}),x={command:"transform",flags:b,inputFS:null!==f,input:null!==f?t(f):"string"==typeof i?t(i):i};w&&(x.mangleCache=w),c(n,x,(e,t)=>{if(e)return a(Error(e),null);let r=X(t.errors,u),n=X(t.warnings,u),i=1,s=()=>{if(0==--i){let e={warnings:n,code:t.code,map:t.map,mangleCache:void 0,legalComments:void 0};"legalComments"in t&&(e.legalComments=null==t?void 0:t.legalComments),t.mangleCache&&(e.mangleCache=null==t?void 0:t.mangleCache),a(null,e)}};if(r.length>0)return a(K("Transform failed",r,n),null);t.codeFS&&(i++,l.readFile(t.code,(e,r)=>{null!==e?a(e,null):(t.code=r,s())})),t.mapFS&&(i++,l.readFile(t.map,(e,r)=>{null!==e?a(e,null):(t.map=r,s())})),s()})}catch(i){let t=[];try{B(t,s,{},o,E)}catch(e){}let r=H(i,e,u,void 0,"");c(n,{command:"error",flags:t,error:r},()=>{r.detail=u.load(r.detail),a(K("Transform failed",[r],[]),null)})}};if(("string"==typeof i||i instanceof Uint8Array)&&i.length>1048576){let e=f;f=()=>l.writeFile(i,e)}f(null)},formatMessages:({callName:e,refs:t,messages:r,options:n,callback:i})=>{if(!n)throw Error(`Missing second argument in ${e}() call`);let s={},o=V(n,s,"kind",_),l=V(n,s,"color",O),a=V(n,s,"terminalWidth",$);if(L(n,s,`in ${e}() call`),void 0===o)throw Error(`Missing "kind" in ${e}() call`);if("error"!==o&&"warning"!==o)throw Error(`Expected "kind" to be "error" or "warning" in ${e}() call`);let u={command:"format-msgs",messages:Z(r,"messages",null,"",a),isWarning:"warning"===o};void 0!==l&&(u.color=l),void 0!==a&&(u.terminalWidth=a),c(t,u,(e,t)=>{if(e)return i(Error(e),null);i(null,t.messages)})},analyzeMetafile:({callName:e,refs:t,metafile:r,options:n,callback:i})=>{void 0===n&&(n={});let s={},o=V(n,s,"color",O),l=V(n,s,"verbose",O);L(n,s,`in ${e}() call`);let a={command:"analyze-metafile",metafile:r};void 0!==o&&(a.color=o),void 0!==l&&(a.verbose=l),c(t,a,(e,t)=>{if(e)return i(Error(e),null);i(null,t.result)})}}}}({writeToStdin(e){a.postMessage(e)},isSync:!1,hasFS:!1,esbuild:h});yield m,o=()=>{a.terminate(),s=void 0,o=void 0,l=void 0},l={build:e=>new Promise((t,r)=>{p.then(r),j.buildOrContext({callName:"build",refs:null,options:e,isTTY:!1,defaultWD:"/",callback:(e,n)=>e?r(e):t(n)})}),context:e=>new Promise((t,r)=>{p.then(r),j.buildOrContext({callName:"context",refs:null,options:e,isTTY:!1,defaultWD:"/",callback:(e,n)=>e?r(e):t(n)})}),transform:(e,t)=>new Promise((r,n)=>{p.then(n),j.transform({callName:"transform",refs:null,input:e,options:t||{},isTTY:!1,fs:{readFile(e,t){t(Error("Internal error"),null)},writeFile(e,t){t(null)}},callback:(e,t)=>e?n(e):r(t)})}),formatMessages:(e,t)=>new Promise((r,n)=>{p.then(n),j.formatMessages({callName:"formatMessages",refs:null,messages:e,options:t,callback:(e,t)=>e?n(e):r(t)})}),analyzeMetafile:(e,t)=>new Promise((r,n)=>{p.then(n),j.analyzeMetafile({callName:"analyzeMetafile",refs:null,metafile:"string"==typeof e?e:JSON.stringify(e),options:t,callback:(e,t)=>e?n(e):r(t)})})}}),eg=h})(e)},58800:(e,t,r)=>{"use strict";let n;r.d(t,{e:()=>S});var i=r(12115),s=r.t(i,2),o=r(3976),l=r(36667),a=r(35409),u=r(90722),c=r(19887);function f(){let e,t=(e="undefined"==typeof document,(0,s.useSyncExternalStore)(()=>()=>{},()=>!1,()=>!e)),[r,n]=i.useState(c._.isHandoffComplete);return r&&!1===c._.isHandoffComplete&&n(!1),i.useEffect(()=>{!0!==r&&n(!0)},[r]),i.useEffect(()=>c._.handoff(),[]),!t&&r}var d=r(14695),h=r(86645),p=r(27579),m=r(54429),g=r(84465),y=r(82728);function v(e){var t;return!!(e.enter||e.enterFrom||e.enterTo||e.leave||e.leaveFrom||e.leaveTo)||!(0,y.zv)(null!=(t=e.as)?t:k)||1===i.Children.count(e.children)}let b=(0,i.createContext)(null);b.displayName="TransitionContext";var w=((n=w||{}).Visible="visible",n.Hidden="hidden",n);let x=(0,i.createContext)(null);function E(e){return"children"in e?E(e.children):e.current.filter(({el:e})=>null!==e.current).filter(({state:e})=>"visible"===e).length>0}function j(e,t){let r,n=(0,u.Y)(e),s=(0,i.useRef)([]),c=(r=(0,i.useRef)(!1),(0,a.s)(()=>(r.current=!0,()=>{r.current=!1}),[]),r),f=(0,o.L)(),d=(0,l._)((e,t=y.mK.Hidden)=>{let r=s.current.findIndex(({el:t})=>t===e);-1!==r&&((0,g.Y)(t,{[y.mK.Unmount](){s.current.splice(r,1)},[y.mK.Hidden](){s.current[r].state="hidden"}}),f.microTask(()=>{var e;!E(s)&&c.current&&(null==(e=n.current)||e.call(n))}))}),h=(0,l._)(e=>{let t=s.current.find(({el:t})=>t===e);return t?"visible"!==t.state&&(t.state="visible"):s.current.push({el:e,state:"visible"}),()=>d(e,y.mK.Unmount)}),p=(0,i.useRef)([]),m=(0,i.useRef)(Promise.resolve()),v=(0,i.useRef)({enter:[],leave:[]}),b=(0,l._)((e,r,n)=>{p.current.splice(0),t&&(t.chains.current[r]=t.chains.current[r].filter(([t])=>t!==e)),null==t||t.chains.current[r].push([e,new Promise(e=>{p.current.push(e)})]),null==t||t.chains.current[r].push([e,new Promise(e=>{Promise.all(v.current[r].map(([e,t])=>t)).then(()=>e())})]),"enter"===r?m.current=m.current.then(()=>null==t?void 0:t.wait.current).then(()=>n(r)):n(r)}),w=(0,l._)((e,t,r)=>{Promise.all(v.current[t].splice(0).map(([e,t])=>t)).then(()=>{var e;null==(e=p.current.shift())||e()}).then(()=>r(t))});return(0,i.useMemo)(()=>({children:s,register:h,unregister:d,onStart:b,onStop:w,wait:m,chains:v}),[h,d,s,b,w,v,m])}x.displayName="NestingContext";let k=i.Fragment,O=y.Ac.RenderStrategy,_=(0,y.FX)(function(e,t){let{show:r,appear:n=!1,unmount:s=!0,...o}=e,u=(0,i.useRef)(null),c=v(e),h=(0,d.P)(...c?[u,t]:null===t?[]:[t]);f();let m=(0,p.O_)();if(void 0===r&&null!==m&&(r=(m&p.Uw.Open)===p.Uw.Open),void 0===r)throw Error("A <Transition /> is used but it is missing a `show={true | false}` prop.");let[g,w]=(0,i.useState)(r?"visible":"hidden"),k=j(()=>{r||w("hidden")}),[_,$]=(0,i.useState)(!0),S=(0,i.useRef)([r]);(0,a.s)(()=>{!1!==_&&S.current[S.current.length-1]!==r&&(S.current.push(r),$(!1))},[S,r]);let P=(0,i.useMemo)(()=>({show:r,appear:n,initial:_}),[r,n,_]);(0,a.s)(()=>{r?w("visible"):E(k)||null===u.current||w("hidden")},[r,k]);let R={unmount:s},C=(0,l._)(()=>{var t;_&&$(!1),null==(t=e.beforeEnter)||t.call(e)}),M=(0,l._)(()=>{var t;_&&$(!1),null==(t=e.beforeLeave)||t.call(e)}),I=(0,y.Ci)();return i.createElement(x.Provider,{value:k},i.createElement(b.Provider,{value:P},I({ourProps:{...R,as:i.Fragment,children:i.createElement(T,{ref:h,...R,...o,beforeEnter:C,beforeLeave:M})},theirProps:{},defaultTag:i.Fragment,features:O,visible:"visible"===g,name:"Transition"})))}),T=(0,y.FX)(function(e,t){var r,n;let{transition:s=!0,beforeEnter:o,afterEnter:u,beforeLeave:c,afterLeave:w,enter:_,enterFrom:T,enterTo:$,entered:S,leave:P,leaveFrom:R,leaveTo:C,...M}=e,[I,U]=(0,i.useState)(null),A=(0,i.useRef)(null),D=v(e),N=(0,d.P)(...D?[A,t,U]:null===t?[]:[t]),F=null==(r=M.unmount)||r?y.mK.Unmount:y.mK.Hidden,{show:V,appear:L,initial:W}=function(){let e=(0,i.useContext)(b);if(null===e)throw Error("A <Transition.Child /> is used but it is missing a parent <Transition /> or <Transition.Root />.");return e}(),[B,z]=(0,i.useState)(V?"visible":"hidden"),q=function(){let e=(0,i.useContext)(x);if(null===e)throw Error("A <Transition.Child /> is used but it is missing a parent <Transition /> or <Transition.Root />.");return e}(),{register:G,unregister:Y}=q;(0,a.s)(()=>G(A),[G,A]),(0,a.s)(()=>{if(F===y.mK.Hidden&&A.current)return V&&"visible"!==B?void z("visible"):(0,g.Y)(B,{hidden:()=>Y(A),visible:()=>G(A)})},[B,A,G,Y,V,F]);let H=f();(0,a.s)(()=>{if(D&&H&&"visible"===B&&null===A.current)throw Error("Did you forget to passthrough the `ref` to the actual DOM node?")},[A,B,H,D]);let J=W&&!L,K=L&&V&&W,X=(0,i.useRef)(!1),Q=j(()=>{X.current||(z("hidden"),Y(A))},q),Z=(0,l._)(e=>{X.current=!0,Q.onStart(A,e?"enter":"leave",e=>{"enter"===e?null==o||o():"leave"===e&&(null==c||c())})}),ee=(0,l._)(e=>{let t=e?"enter":"leave";X.current=!1,Q.onStop(A,t,e=>{"enter"===e?null==u||u():"leave"===e&&(null==w||w())}),"leave"!==t||E(Q)||(z("hidden"),Y(A))});(0,i.useEffect)(()=>{D&&s||(Z(V),ee(V))},[V,D,s]);let et=!(!s||!D||!H||J),[,er]=(0,h.p)(et,I,V,{start:Z,end:ee}),en=(0,y.oE)({ref:N,className:(null==(n=(0,m.x)(M.className,K&&_,K&&T,er.enter&&_,er.enter&&er.closed&&T,er.enter&&!er.closed&&$,er.leave&&P,er.leave&&!er.closed&&R,er.leave&&er.closed&&C,!er.transition&&V&&S))?void 0:n.trim())||void 0,...(0,h.B)(er)}),ei=0;"visible"===B&&(ei|=p.Uw.Open),"hidden"===B&&(ei|=p.Uw.Closed),V&&"hidden"===B&&(ei|=p.Uw.Opening),V||"visible"!==B||(ei|=p.Uw.Closing);let es=(0,y.Ci)();return i.createElement(x.Provider,{value:Q},i.createElement(p.El,{value:ei},es({ourProps:en,theirProps:M,defaultTag:k,features:O,visible:"visible"===B,name:"Transition.Child"})))}),$=(0,y.FX)(function(e,t){let r=null!==(0,i.useContext)(b),n=null!==(0,p.O_)();return i.createElement(i.Fragment,null,!r&&n?i.createElement(_,{ref:t,...e}):i.createElement(T,{ref:t,...e}))}),S=Object.assign(_,{Child:$,Root:_})}}]);