#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <sys/prctl.h>

struct Entity { char pad[0x4e8]; int max_hp; float hp; char tail[0x13f8-0x4f0]; };
struct Entity player = {.max_hp=100, .hp=100};
struct Entity enemy = {.max_hp=100, .hp=100};
struct Entity minion = {.max_hp=80, .hp=40};
struct Entity foreign_minion = {.max_hp=80, .hp=40};
struct Entity *entity_slot = &player;
unsigned char hero[0x19800];
unsigned char room[0x24b00];
uint32_t key_a=0, key_b=0x12345678, detection=0, penalty=0;
volatile int value=100;
extern void damage(struct Entity *, float);
extern unsigned char damage_store[];
extern void burn(struct Entity *, float);
extern unsigned char dot_damage_store[];
extern void drain(struct Entity *, float);
extern void regen(struct Entity *, float);
extern void energy_cap(struct Entity *, float);
extern unsigned char energy_store[], energy_regen_store[], energy_cap_store[];
static void set32(struct Entity *entity,int offset,uint32_t value) {
    memcpy((char *)entity+offset,&value,4);
}
__attribute__((constructor)) static void init_minions(void) {
    set32(&player,0x58c,42);
    for(int i=0;i<2;i++) {
        struct Entity *pet=i ? &foreign_minion : &minion;
        set32(pet,0x170,4); set32(pet,0x64c,i ? 99 : 42);
        set32(pet,0x178,100); set32(pet,0x608,0x41c80000);
    }
    int count=4; memcpy(room+0xbef0,&count,4);
    struct Entity *entities[]={&player,&enemy,&minion,&foreign_minion};
    memcpy(room+0xbef8,entities,sizeof(entities));
    void *pointer=room; memcpy(hero+0x197c0,&pointer,8);
}
__asm__(
 ".text\n.globl damage\ndamage:\n"
 "push %rbx\nmov %rdi,%rbx\n"
 "movss 0x4ec(%rbx),%xmm2\nsubss %xmm0,%xmm2\n"
 ".globl damage_store\ndamage_store:\n"
 "movss %xmm2,0x4ec(%rbx)\npop %rbx\nret\n"
);
__asm__(
 ".text\n.globl burn\nburn:\n"
 "push %rbx\nmov %rdi,%rbx\n"
 "movss 0x4ec(%rbx),%xmm3\nsubss %xmm0,%xmm3\n"
 ".globl dot_damage_store\ndot_damage_store:\n"
 "movss %xmm3,0x4ec(%rbx)\npop %rbx\nret\n"
);
__asm__(
 ".text\n.globl drain\ndrain:\npush %rbx\nmov %rdi,%rbx\n"
 "movaps %xmm0,%xmm1\nmovss 0x608(%rbx),%xmm0\nsubss %xmm1,%xmm0\n"
 ".globl energy_store\nenergy_store:\nmovss %xmm0,0x608(%rbx)\npop %rbx\nret\n"
 ".globl regen\nregen:\n.globl energy_regen_store\nenergy_regen_store:\n"
 "movss %xmm0,0x608(%rdi)\nret\n"
 ".globl energy_cap\nenergy_cap:\nmovaps %xmm0,%xmm1\n"
 ".globl energy_cap_store\nenergy_cap_store:\nmovss %xmm1,0x608(%rdi)\nret\n"
);
int main(void) {
    prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY, 0, 0, 0);
    int offsets[]={0x160,0x164,0x168,0x16c};
    int mirrors[]={0x17c,0x180,0x184,0x188};
    uint32_t values[]={250,1000,3,5};
    for(int i=0;i<4;i++) {
        memcpy(hero+offsets[i], &values[i], 4);
        uint32_t encoded=values[i]^key_b;
        memcpy(hero+mirrors[i], &encoded, 4);
    }
    printf("{\"pid\":%d,\"value\":%lu,\"hero\":%lu,\"entity_slot\":%lu,"
           "\"primary_key\":%lu,\"mirror_key\":%lu,\"detection_flag\":%lu,"
           "\"penalty_flag\":%lu,\"damage_store\":%lu,\"dot_damage_store\":%lu,"
           "\"energy_store\":%lu,\"energy_regen_store\":%lu,\"energy_cap_store\":%lu}\n",getpid(),
           (unsigned long)&value,(unsigned long)hero,(unsigned long)&entity_slot,
           (unsigned long)&key_a,(unsigned long)&key_b,(unsigned long)&detection,
           (unsigned long)&penalty,(unsigned long)damage_store,
           (unsigned long)dot_damage_store,(unsigned long)energy_store,
           (unsigned long)energy_regen_store,(unsigned long)energy_cap_store);
    fflush(stdout);
    char line[128];
    while(fgets(line,sizeof(line),stdin)) {
        if(strncmp(line,"damage",6)==0) {
            damage(&player,25); damage(&enemy,25);
            printf("%.0f %.0f\n",player.hp,enemy.hp);
        } else if(strncmp(line,"burn",4)==0) {
            burn(&player,10); burn(&enemy,10);
            printf("%.0f %.0f\n",player.hp,enemy.hp);
        } else if(strncmp(line,"pets",4)==0) {
            damage(&minion,10); burn(&minion,5); drain(&minion,10);
            damage(&foreign_minion,10); burn(&foreign_minion,5); drain(&foreign_minion,10);
            float energy,foreign_energy;
            memcpy(&energy,(char *)&minion+0x608,4);
            memcpy(&foreign_energy,(char *)&foreign_minion+0x608,4);
            printf("%.0f %.0f %.0f %.0f\n",minion.hp,energy,foreign_minion.hp,foreign_energy);
        } else if(strncmp(line,"swap",4)==0) {
            entity_slot=&enemy;
            puts("swapped");
        } else if(strncmp(line,"value",5)==0) printf("%d\n",value);
        else if(strncmp(line,"exit",4)==0) break;
        fflush(stdout);
    }
    return 0;
}
