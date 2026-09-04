"""
武打场景生成Demo脚本
功能：自动生成一段跌宕起伏的武打场景，包含前期压制、绝境加深、转机和反杀
"""

from main import generate_fight_scene_with_reversal
import datetime

def generate_demo():
    """生成武打场景demo"""
    
    # 预设一个经典的武打场景提示词
    demo_prompt = """
    场景：两位武林高手在古寺大殿中生死对决
    人物：主角是一位年轻剑客，对手是一位经验丰富的拳法宗师
    环境：殿内烛光摇曳，佛像庄严肃穆，地上散落着破碎的蒲团和木屑
    特殊要求：
    - 主角一开始处于明显劣势，被对手的凌厉拳风压制
    - 对手招式刚猛霸道，擅长贴身近战，拳拳到肉
    - 主角需要依靠剑法的灵动和环境的巧妙利用才能找到转机
    - 要求细节丰富，招式描写具体，心理变化清晰
    """
    
    print("=" * 60)
    print("正在生成武打场景Demo...")
    print("=" * 60)
    print()
    
    try:
        # 调用生成函数
        result = generate_fight_scene_with_reversal(demo_prompt)
        
        # 输出结果
        print("\n" + "=" * 60)
        print("【生成结果】")
        print("=" * 60)
        print()
        print(result)
        print()
        print("=" * 60)
        
        # 保存结果到文件
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"demo_output_{timestamp}.txt"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("武打场景生成Demo结果\n")
            f.write(f"生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            f.write("【提示词】\n")
            f.write(demo_prompt.strip() + "\n\n")
            f.write("=" * 60 + "\n")
            f.write("【生成内容】\n")
            f.write("=" * 60 + "\n\n")
            f.write(result)
        
        print(f"结果已保存到文件：{output_file}")
        print("=" * 60)
        
        return result
        
    except Exception as e:
        print(f"\n生成过程中出错：{e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    print("\n欢迎使用武打场景生成Demo！")
    print("本脚本将自动生成一段包含前期压制、转机和反杀的武打场景。\n")
    
    # 生成demo
    generate_demo()
    
    print("\nDemo生成完成！")

