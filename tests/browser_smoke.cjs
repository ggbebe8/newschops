const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const env=Object.fromEntries(fs.readFileSync('.env','utf8').split('\n').filter(l=>l&&!l.startsWith('#')).map(l=>{const i=l.indexOf('=');return[l.slice(0,i),l.slice(i+1)]}));
  const baseURL=process.env.TEST_BASE_URL||env.APP_ORIGIN||'http://localhost:38475';
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(baseURL);
  await page.locator('input[name=username]').fill(env.ADMIN_USERNAME);
  await page.locator('input[name=password]').fill(env.ADMIN_PASSWORD);
  await page.getByRole('button',{name:'로그인 →',exact:true}).click();
  await page.getByRole('button',{name:'현재 TOP 10',exact:true}).waitFor();
  for(const width of [360,768,1440]){
    await page.setViewportSize({width,height:1000});
    await page.evaluate(()=>document.fonts.ready);
    await page.waitForTimeout(200);
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
    if(overflow)throw Error('horizontal overflow '+width);
    if(width===360)await page.screenshot({path:'/tmp/newschops-mobile.png',fullPage:true});
    if(width===1440)await page.screenshot({path:'/tmp/newschops-desktop.png',fullPage:true});
  }
  await page.getByRole('button',{name:/수집 상태/}).click();
  await page.getByRole('heading',{name:/수집 상태/}).waitFor();
  await page.getByRole('button',{name:/언론사 · 지면/}).click();
  await page.getByRole('heading',{name:'동아일보 실제 지면 목차'}).waitFor();
  await page.getByRole('button',{name:/개인 설정/}).click();
  await page.getByRole('heading',{name:'나에게 맞는 뉴스'}).waitFor();
  const manifest=await page.request.get(baseURL+'/manifest.webmanifest');
  const data=await manifest.json();if(data.icons.length!==3)throw Error('manifest icons');
  for(const icon of data.icons){if(!(await page.request.get(baseURL+icon.src)).ok())throw Error('missing icon')}
  await page.getByRole('button',{name:'로그아웃',exact:true}).click();
  await page.getByRole('button',{name:'로그인 →',exact:true}).waitFor();
  if((await page.request.get(baseURL+'/api/me')).status()!==401)throw Error('logout session');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: login, admin navigation, settings, 360/768/1440 overflow, manifest/icons, logout; page errors=0');
  await browser.close();
})().catch(e=>{console.error(e.message);process.exit(1)});
