"""Exercise the real embedded Flower manager with a deterministic clock/random source."""
import os, shlex, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BOARD=ROOT/'main/boards/flower-s3'

class FlowerRandomPlayerTest(unittest.TestCase):
    def test_embedded_groups_sessions_and_failed_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            (folder/'esp_random.h').write_text('#pragma once\n#include <cstdint>\ninline uint32_t value=0; inline uint32_t esp_random(){return value;}\n')
            (folder/'application.h').write_text(r'''#pragma once
#include <string_view>
#include <string>
constexpr int kDeviceStateIdle=0;
inline bool idle=true, accepted=true;
inline int state=0,calls=0;
inline std::string last;
class AudioService { public: bool IsPlaybackIdle(){return idle;} };
class Application { AudioService audio_; public:
static Application& GetInstance(){static Application app;return app;}
int GetDeviceState(){return state;} AudioService& GetAudioService(){return audio_;}
bool PlayLocalAudio(std::string_view sound){++calls;last=sound;return accepted && !sound.empty();}
};''')
            header=['#pragma once','#include <array>','#include <string_view>',
                    'namespace Flower::Sounds {struct Clip{std::string_view data;int id;};',
                    'inline constexpr bool AUTOMATIC_ENABLED=true,GREETING_MORNING_ENABLED=true,GREETING_NIGHT_ENABLED=true;',
                    'inline constexpr std::string_view GREETING_MORNING="morning",GREETING_NIGHT="night";']
            for group,count,offset in [('CLOCK',12,0),('PHRASE_ANYTIME',10,100),('PHRASE_MORNING',4,200),('PHRASE_AFTERNOON',4,300),('PHRASE_EVENING',4,400),('SESSION_START',3,500),('SESSION_END',3,600)]:
                values=','.join('{"%s-%d",%d}'%(group,i,offset+i) for i in range(count))
                header.append('inline const std::array<Clip,%d> %s{{%s}};'%(count,group,values))
            (folder/'flower_audio_assets.h').write_text('\n'.join(header+['}']))
            driver=folder/'test.cc'
            driver.write_text(r'''#include "flower_audio_manager.h"
#include "application.h"
#include "esp_random.h"
#include <cassert>
#include <ctime>
#include <cstdlib>
inline std::time_t now=0;
extern "C" std::time_t time(std::time_t* out) noexcept {if(out){*out=now;} return now;}
int main(){
flower::FlowerAudioManager manager;
setenv("TZ","CST-8",1);tzset();
std::string previous;
for(int hour : {0,5,6,11,12,17,18,23}){
now=1762041600+hour*3600;
const std::string group=hour<6||hour>=18?"PHRASE_EVENING":hour<12?"PHRASE_MORNING":"PHRASE_AFTERNOON";
for(int i=0;i<64;++i){value=i;manager.PlayPhrase();assert(last.starts_with("PHRASE_ANYTIME")||last.starts_with(group));assert(last!=previous);previous=last;}}
now=0;manager.PlayPhrase();assert(last.starts_with("PHRASE_ANYTIME"));
int before=calls;state=1;manager.PlayPhrase();assert(calls==before);state=0;
idle=false;manager.PlayPhrase();assert(calls==before);idle=true;
value=0;auto first=manager.SessionSound(true);manager.CommitSessionSound(true);
auto next=manager.SessionSound(true);assert(first!=next);
assert(manager.SessionSound(true)==next); // no commit on failed start
manager.CommitSessionSound(true);assert(manager.SessionSound(true)!=next);
assert(manager.SessionSound(false).starts_with("SESSION_END"));
manager.PlayClock(11);assert(last=="CLOCK-11");assert(!manager.PlayClock(12));
manager.PlayGreeting(true);assert(last=="morning");
}''')
            command=shlex.split(os.environ.get('CXX','c++'))+['-std=c++20','-Wall','-Wextra','-Werror',f'-I{folder}',f'-I{BOARD}',str(driver),str(BOARD/'flower_audio_manager.cc'),'-o',str(folder/'test')]
            subprocess.run(command,check=True)
            subprocess.run([str(folder/'test')],check=True)

if __name__=='__main__': unittest.main()
