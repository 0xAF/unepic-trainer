/* Owned campaign fixture: native protected setters and one update entry. */
#include <assert.h>
#define main unused_fixture_main
#include "target.c"
#undef main

uint32_t campaign_mode = 0, simulation_flag = 0;
uint32_t progression_calls = 0;
unsigned char item_table[0xb9404];
uint32_t gold_calls = 0;
uint32_t custom_map = 0, player_count = 1;
void *active_hero = hero;
int32_t credit_scores[16] = {500,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-1};
int32_t credit_types[15] = {2};
int credits_fixture_enabled = 0;
void update_credits(void *character);
extern void character_update(void *);
__asm__(".text\n.globl character_update\ncharacter_update:\n"
        "push %r14\npush %r13\npush %r12\npush %rbp\npush %rbx\n"
        "call update_credits\n"
        "pop %rbx\npop %rbp\npop %r12\npop %r13\npop %r14\nret\n");

static uint32_t decoded(void *character,int offset) {
    uint32_t value; memcpy(&value,(char *)character+offset,4); return value^key_a;
}
static void pair(void *character,int offset,int mirror,uint32_t value) {
    uint32_t a=value^key_a,b=value^key_b;
    memcpy((char *)character+offset,&a,4); memcpy((char *)character+mirror,&b,4);
}
void points_add(void *character,int delta) {
    progression_calls++; pair(character,0x16c,0x188,decoded(character,0x16c)+delta);
}
int xp_cap(void *character) { return decoded(character,0x164); }
void xp_set(void *character,int value) { pair(character,0x160,0x17c,value); }
void xp_award(void *character,int delta) {
    progression_calls++;
    if (simulation_flag || !delta) return;
    /* Model the campaign's low award rounding to zero for an overleveled hero. */
    uint32_t current=decoded(character,0x160),cap=xp_cap(character);
    if(current>=cap && decoded(character,0x168)<25) {
        pair(character,0x168,0x184,decoded(character,0x168)+1);
        pair(character,0x160,0x17c,current-cap);
        pair(character,0x164,0x180,cap*2);
        pair(character,0x16c,0x188,decoded(character,0x16c)+5);
        player.hp=player.max_hp;
    }
}
__attribute__((constructor)) static void init_progression(void) {
    pair(hero,0x160,0x17c,250); pair(hero,0x164,0x180,1000);
    pair(hero,0x168,0x184,3); pair(hero,0x16c,0x188,5);
    uint32_t count=1,descriptors=2,id=0x238d,credit_id=0x238e,cap=1000000;
    memcpy(item_table+0xb9400,&descriptors,4); memcpy(item_table,&id,4);
    memcpy(item_table+4,"gold",5); memcpy(item_table+0x70,&cap,4);
    memcpy(item_table+0x1c8,&credit_id,4); memcpy(item_table+0x1cc,"credits",8);
    memcpy(item_table+0x238,&cap,4);
    memcpy(hero+0x140c,&count,4);
    void *descriptor=item_table; memcpy(hero+0x1418,&descriptor,8);
    pair(hero+0x1418,8,0x34,250); pair(hero+0x1418,0x10,0x38,0);
    pair(hero+0x1418,0x18,0x3c,100); pair(hero+0x1418,0x24,0x40,0);
}

/* Normal update recalculates credits from the saved source counter. */
void update_credits(void *character) {
    if(!credits_fixture_enabled || character!=hero) return;
    int32_t spent,total=0; memcpy(&spent,hero+0x170,4);
    for(int i=0;i<15;i++) if(credit_types[i]==2) total+=credit_scores[i];
    uint32_t count; memcpy(&count,hero+0x140c,4);
    unsigned char *entry=NULL;
    for(uint32_t i=0;i<count;i++) {
        void *pointer; memcpy(&pointer,hero+0x1418+i*0xb8,8);
        if(pointer==item_table+0x1c8) entry=hero+0x1418+i*0xb8;
    }
    if(!entry) {
        assert(count<512); entry=hero+0x1418+count*0xb8; memset(entry,0,0xb8);
        void *pointer=item_table+0x1c8; memcpy(entry,&pointer,8);
        pair(entry,0x10,0x38,0); pair(entry,0x18,0x3c,100); pair(entry,0x24,0x40,0);
        count++; memcpy(hero+0x140c,&count,4);
    }
    pair(entry,8,0x34,total-spent);
}

/* Model the normal award's existing-stack and initially empty cases. */
void *item_add(void *inventory,const char *name,int x,int y,int amount) {
    assert(!strcmp(name,"gold") && !x && !y && amount>0);
    assert(inventory==hero+0x1400);
    uint32_t count; memcpy(&count,(char *)inventory+0xc,4);
    void *entry=(char *)inventory+0x18;
    if(!count) {
        count=1; memcpy((char *)inventory+0xc,&count,4);
        void *descriptor=item_table; memcpy(entry,&descriptor,8);
        pair(entry,8,0x34,0); pair(entry,0x10,0x38,0);
        pair(entry,0x18,0x3c,100); pair(entry,0x24,0x40,0);
    }
    pair(entry,8,0x34,decoded(entry,8)+amount); gold_calls++;
    return entry;
}

#ifdef PROGRESSION_PROCESS
int main(void) {
    prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY, 0, 0, 0);
    puts("ready"); fflush(stdout);
    char line[64];
    while(fgets(line,sizeof(line),stdin)) {
        if(strncmp(line,"update",6)==0) {
            character_update(hero);
            printf("%u %u %u\n",decoded(hero,0x168),decoded(hero,0x160),decoded(hero,0x16c));
            fflush(stdout);
        } else if(strncmp(line,"exit",4)==0) break;
    }
    return 0;
}
#endif
