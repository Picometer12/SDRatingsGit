import math
import os
from collections import namedtuple
from copy import copy
import random

import modules.scripts as scripts
import gradio as gr

from modules import images
from modules.processing import process_images, Processed
from modules.shared import opts, cmd_opts, state
import modules.sd_samplers

# is there a better way to do this?
#group = "defaultgroup"
groups = ["defaultGroupList"]

keyword1 = "defaulta"
keyword2 = "defaultb"
keywordList = []

state = "noComparison" #can be noComparison, ready, rated, errorGenerating

oldInputs = ["", ""] #used to see if settings have changed

eloScale = 32 #used in elo algorithm. This is the max change in elo rating. 
useNewcomerEloMultiplier = True

#used in displaying the images that need to be rated, separate from generation image area
#imagesToRate = []
#ratingImageUI = 



def draw_xy_grid(xs, ys, x_label, y_label, cell):
    res = []

    ver_texts = [[images.GridAnnotation(y_label(y))] for y in ys]
    #ver_texts = ["", "", ""]
    hor_texts = [[images.GridAnnotation(x_label(x))] for x in xs]

    first_processed = None

    state.job_count = len(xs) * len(ys)

    for iy, y in enumerate(ys):
        for ix, x in enumerate(xs):
            state.job = f"{ix + iy * len(xs) + 1} out of {len(xs) * len(ys)}"

            processed = cell(x, y)
            if first_processed is None:
                first_processed = processed

            res.append(processed.images[0])

    grid = images.image_grid(res, rows=len(ys))
    #grid = images.draw_grid_annotations(grid, res[0].width, res[0].height, hor_texts, ver_texts)
    grid = images.draw_grid_annotations(grid, res[0].width, res[0].height, hor_texts, ver_texts)
    

    first_processed.images = [grid]

    return first_processed


#Gradio doesnt like it when I pass strings using button click inputs, so we're doing it this way
def voteLeft():
    global state

    #Todo make the error  messages readable within gradio app
    if state == "ready":
        ratingAdjust("left")
        state = "rated"
    elif state == "noComparison":
        raise gr.Error("Nothing to rate, generate images first")
    elif state == "rated":
        raise gr.Error("Already rated, generate new images first.")
    else:
        raise gr.Error("Bad Developer. Variable state should only take values of noComparison, ready, or rated")

def voteRight():
    global state
    
    if state == "ready":
        ratingAdjust("right")
        state = "rated"
    elif state == "noComparison":
        raise gr.Error("Nothing to rate, generate images first")
    elif state == "rated":
        raise gr.Error("Already rated, generate new images first.")
    else:
        raise gr.Error("Bad Developer. Variable state should only take values of noComparison, ready, or rated")

def doOver():
    global state, keywordList
    #keywordList.insert(0, keyword2)
    #keywordList.insert(0, keyword1)
    state = "noComparison"
    #Todo: figure out how to generate from button push

#def updateRatingImageUI():
#    ratingImageUI.value = imagesToRate[0]


def ratingAdjust(txtWinner):
    print(txtWinner + " wins")
    
    global keywordList

    #could do all groups at once, but I've already written this for one so let's just reuse it
    def getElo(keyword, group):
        file_dir = os.path.dirname(os.path.realpath("__file__"))
        read_file = os.path.join(file_dir, f"scripts/SDRatings/SDRatings.txt")    
        if os.path.exists(read_file):
            with open(read_file, 'r') as f:
                
                #if a line contains group, return keyword from format keyword(group1:1500, group2:1500,...)
                #if two colons between commas, second number is number of ratings. keyword(group1:1500:2)
                for line in f.read().strip().splitlines():  
                    #remove the ending parentheses
                    line = line[:-1]
                    if keyword in line:
                        groupString = line.split("(")[1]
                        groupList = groupString.split(",")
                        
                        #data is in the form groupName:1500 or groupName:1500:2
                        for grp in groupList:
                            if group in grp:
                                return grp.split(":",1)[1]

                f.close()
        #if we get to this point, there's a problem
        raise gr.Error("getEloNew didnt find the group within the keyword")
        return 0




        #Todo: If this is slow, try to save something in the getElo method that will help us SetElo faster
        #I'm guessing this sort of thing is not slow on this scale

    def setElo(keyword, group, newElo, timesRated):
        file_dir = os.path.dirname(os.path.realpath("__file__"))
        read_file = os.path.join(file_dir, f"scripts/SDRatings/SDRatings.txt")    
        if os.path.exists(read_file):
            with open(read_file, 'r') as f:
                
                #I'm sure there's a better way to do this than opening and closing in different modes
                replacedContent = ""
                
                #lines are in format Anton Fadeev(Overall:1500, ConceptArtists:1500)
                for line in f.read().strip().splitlines():
                    #line = line.strip()

                    if keyword in line:
                        #remove the parentheses on the end
                        line = line[:-1]
                        #add the keyword back in 
                        replacedContent += line.split("(")[0] + "("

                        groupString = line.split("(")[1]
                        groupList = groupString.split(",")

                        #grp in form Overall:1500:1 if has been updated. Could be Overall:1500 in else
                        for grp in groupList:
                            if group in grp:
                                #add in the keyword then the new rating
                                replacedContent += grp.split(":")[0] + ":" + str(newElo) + ":" + str(timesRated) + ","

                            else:
                                replacedContent += grp + ","

                        #remove the extra comma and add a ) and new line.
                        replacedContent = replacedContent[:-1] + ")\n" 
                    else:
                        replacedContent += line + "\n"
                            
                f.close()
                replacedContent.strip()
                    
            with open(read_file, 'w') as f:
                f.writelines(replacedContent)
                f.close()

    eloRatingChunks1 = []
    eloRatingChunks2 = []
    originalElos1 = []
    originalElos2 = []
    timesRated1 = []
    timesRated2 = []
    expectedLeftWinProb = []
    newElos1 = []
    newElos2 = []
    eloMultipliers1 = []
    eloMultipliers2 = []
    #eloScales = []

    #constants for elo algorithm. Todo: make this configurable, or scale with number of comparisons
    differenceParam = 400 #elo guide recommends 400. Figure out what this actually means -- does this mean that a 400 pt difference means something
    #eloScale = 32 #this is now global and configurable

    if txtWinner == "left":
        winLeftBinary = 1
        print(keyword1 + " wins")
    elif txtWinner == "right":
        winLeftBinary = 0
        print(keyword2 + " wins")
    else:
        #Todo throw a proper error message into automatic1111
        print("txtWinner should be left or right")

    i = 0
    for group in groups:
        #get elo returns can return "Artist" or "Artist:1"
        
        eloRatingChunks1.append(getElo(keyword1, group).split(":"))
        eloRatingChunks2.append(getElo(keyword2, group).split(":"))

        originalElos1.append(int(eloRatingChunks1[i][0]))
        originalElos2.append(int(eloRatingChunks2[i][0]))

        #Todo: would be cleaner for chunks to be temporary instead of an array

        if len(eloRatingChunks1[i]) == 1:
            timesRated1.append(1)
        else:
            timesRated1.append(int(eloRatingChunks1[i][1]))

        if len(eloRatingChunks2[i]) == 1:
            timesRated2.append(1)
        else:
            timesRated2.append(int(eloRatingChunks2[i][1]))

        if useNewcomerEloMultiplier:
            eloMultipliers1.append(max(1,int (5.5 - 0.5*timesRated1[i])))
            eloMultipliers2.append(max(1,int (5.5 - 0.5*timesRated1[i])))



        expectedLeftWinProb.append( 1/(1 + pow(10, (originalElos2[i] - originalElos1[i])/differenceParam)))

        newElos1.append(round(originalElos1[i] + eloScale*eloMultipliers1[i]*(winLeftBinary - expectedLeftWinProb[i])))
        newElos2.append(round(originalElos2[i] - eloScale*eloMultipliers1[i]*(winLeftBinary - expectedLeftWinProb[i])))

        timesRated1[i] += 1
        timesRated2[i] += 1

        setElo(keyword1, group, newElos1[i], timesRated1[i])
        setElo(keyword2, group, newElos2[i], timesRated2[i])

        print(keyword1 + ":" + group + " changed from " + str(originalElos1[i]) + " to " + str(newElos1[i])) 
        print(keyword2 + ":" + group + " changed from " + str(originalElos2[i]) + " to " + str(newElos2[i]))
        

        i += 1
    
    #get rid of the first two elements
    keywordList.pop(0)
    keywordList.pop(0)





class Script(scripts.Script):
    def title(self):
        return "SDRatings"

    def ui(self, is_img2img):
        
        #global ratingImageUI

        gr.Markdown(" Vote for the left or right keyword after image generation") #add some vertical white space
        with gr.Row():
            left_wins = gr.Button(value = "Vote Left")
            cant_decide = gr.Button(value = "Can't Decide") #probably can just take this out since we can just generate again
            right_wins = gr.Button(value = "Vote Right")

        left_wins.click(voteLeft)
        cant_decide.click(doOver)
        right_wins.click(voteRight)
        
        #if len(imagesToRate) > 0:
        #    ratingImageUI = gr.Image(value = imagesToRate[0])
        #else:
        #    ratingImageUI = gr.Image()

        #Todo: figure out how to make a separate image window for displaying grids to be rated

        #ratingImageUI = gr.Image()
        #ratingImageUI.change(updateRatingImageUI)

        gr.Markdown(" <br/> ") #add some vertical white space

        

        #Todo: get rid of this without breaking
        
        #put_at_start = gr.Checkbox(label='Put variable parts at start of prompt', value=False)
        #number_of_comparisons = gr.Number(label="Number of Images per keyword (integer)", value = 3, precision = 0)
        #Todo: make this a number, but I couldn't get it to work
        
        gr.Markdown("Fill this out before image generation. ") #add some vertical white space
        gr.Markdown(" <br/> ") 
        
        with gr.Row():
            keywordGroups = gr.Textbox(label="Rated Groups - each of these tags will be rated", value = "Overall,RealisticArtist")
            unratedGroups = gr.Textbox(label="Unrated Groups - used as filter but will not be rated ", value = "")

        
        gr.Markdown("Remove an unwanted tag here after image generation.  ") #add some vertical white space
        gr.Markdown(" <br/> ") 

        with gr.Row():
            removeTagInput = gr.Textbox(label="Name of tag to be removed")
            removeTagLeftButton = gr.Button(value = "Remove from left keyword")
            removeTagRightButton = gr.Button(value = "Remove from right keyword")
        

        #left_wins.click(voteLeft)
        #cant_decide.click(doOver)
        #right_wins.click(voteRight)

        #with gr.Row():
            #addRemoveDropdownSelection = gr.Dropdown(label="Add or Remove tags", choices=["add", "remove"], value= "add", type="value", interactive = True)
            #type index returns index of choice selected. Type value returns string.
            #tagDropdownSelection = gr.Dropdown(label="Tags", choices=[groups], type="index")
            #tagDropdownSelection = gr.Dropdown(label="Choose keywords", choices=["add", "remove"], value=current_axis_options[1].label, type="index", elem_id=self.elem_id("x_type"))
            #x_values = gr.Textbox(label="X values", lines=1, elem_id=self.elem_id("x_values"))

        #with gr.Row():
        #    x_type = gr.Dropdown(label="X type", choices=[x.label for x in current_axis_options], value=current_axis_options[1].label, type="index", elem_id=self.elem_id("x_type"))
        #    x_values = gr.Textbox(label="X values", lines=1, elem_id=self.elem_id("x_values"))
        
        
        #left_wins = gr.Button(value = "Vote Left")
        #cant_decide = gr.Button(value = "Can't Decide") #probably can just take this out since we can just generate again
        #right_wins = gr.Button(value = "Vote Right")

        #left_wins.click(voteLeft)
        #cant_decide.click(doOver)
        #right_wins.click(voteRight)

        gr.Markdown("Miscellaneous Settings ") #add some vertical white space
        gr.Markdown(" <br/> ") 

        number_of_comparisons = gr.Textbox(label="Number of Images per keyword (integer)", value = 3)
        eloScaleInput = gr.Slider(label = "Max elo change. Even ratings will occur by half this amount. Not recommended to change.", minimum = 32, maximum = 50, value = 32, )
        useNewcomerEloMultiplierInput = gr.Checkbox(label = "Increase eloScale by up to 5 for tags with few ratings.", value = True)
    
        #different_seeds = gr.Checkbox(label='Use different seed for each picture', value=False)

        return [ number_of_comparisons, keywordGroups, unratedGroups, eloScaleInput, useNewcomerEloMultiplierInput ]

    def run(self, p, number_of_comparisons, keywordGroups, unratedGroups, eloScaleInput, useNewcomerEloMultiplierInput):
        modules.processing.fix_seed(p)

        global groups, state, eloScale, newcomeEloMultiplier

        groups = keywordGroups.split(",")
        unratedGroupList = unratedGroups.split(",")
        eloScale = int(eloScaleInput)
        useNewcomerEloMultiplier = useNewcomerEloMultiplierInput

        for group in groups:
            group = group.strip()

        for group in unratedGroupList:
            group = group.strip()
        
        def replace_wildcard(chunk):
            if " " not in chunk:
                file_dir = os.path.dirname(os.path.realpath("__file__"))
                replacement_file = os.path.join(file_dir, f"scripts/wildcards/{chunk}.txt")
                if os.path.exists(replacement_file):
                    with open(replacement_file, encoding="utf8") as f:
                        return random.choice(f.read().splitlines())
            return chunk

        def populateKeywordList():
            keywords = []
            
            file_dir = os.path.dirname(os.path.realpath("__file__"))
            read_file = os.path.join(file_dir, f"scripts/SDRatings/SDRatings.txt")
            
            if os.path.exists(read_file):
                with open(read_file, 'r') as f:
                    #if a line contains all specified groups, return keyword from format keyword(group1, group2,...)
                    for line in f.read().splitlines():
                        keep = True
                        for group in groups + unratedGroupList:
                            if group not in line:
                                keep = False
                        
                        if keep:
                            keeper = line.split("(")[0]
                            keeper = keeper.strip()
                            keywords.append(keeper)
                
                    f.close()
            random.shuffle(keywords)

            return keywords

        #Don't know why I was having issues with Number instead of textbox, my workaround
        number_of_comparisons = int(number_of_comparisons)

        original_prompt = p.prompt[0] if type(p.prompt) == list else p.prompt

        all_prompts = []
        #prompt_matrix_parts = original_prompt.split("|")
        #combination_count = 2 ** (len(prompt_matrix_parts) - 1)

        global keyword1, keyword2, keywordList
        #global imagesToRate
        global oldInputs
        
        #determine if settings have changed, record these settings to compare next time
        if oldInputs[0] == keywordGroups and oldInputs[1] == unratedGroups:
            newSettings = False
        else:
            newSettings = True

        oldInputs = [keywordGroups, unratedGroups]

        #Repopulate keyword queue if settings have changed or there aren't enough in the list
        

        if len(keywordList) < 2 or newSettings:
            print("New Keywords!")
            keywordList = populateKeywordList()
            if len(keywordList) < 2:
                #state = "errorGenerating"
                
                keyword1 = "defaulta"
                keyword2 = "defaultb"
                raise gr.Error("There aren't two or more keywords with the group")
        
        #Todo: do something if data is not valid

        #keyword1 = keywordList.pop()
        #keyword2 = keywordList.pop()

        keyword1 = keywordList[0]
        keyword2 = keywordList[1]

        #from wildcards
        #all_prompts = ["".join(replace_wildcard(chunk) for chunk in original_prompt.split("__")) for _ in range(p.batch_size * p.n_iter)]

        #modified for my script -- Todo think about how to handle anything besides batch size = 1
        #I only need one wildcard prompt for now
        wildcardPrompt = "".join(replace_wildcard(chunk) for chunk in original_prompt.split("__"))

        for i in range(number_of_comparisons):
            #selected_prompts = original_prompt.replace("keyword", keyword1)
            selected_prompts = wildcardPrompt.replace("keyword", keyword1)
            all_prompts.append(selected_prompts)


            #selected_prompts = original_prompt.replace("keyword", keyword2)
            selected_prompts = wildcardPrompt.replace("keyword", keyword2)
            all_prompts.append(selected_prompts)

       #Todo: check if metadata is not correct due to either my logic or wildcard logic 
        


        p.n_iter = math.ceil(len(all_prompts) / p.batch_size)
        p.do_not_save_grid = True

        # print(f"Prompt matrix will create {len(all_prompts)} images using a total of {p.n_iter} batches.")

        p.prompt = all_prompts
        #p.seed = [p.seed + (i if different_seeds else 0) for i in range(len(all_prompts))]
        p.seed = [p.seed + (i / 2) for i in range(len(all_prompts))]
        p.prompt_for_display = original_prompt
        processed = process_images(p)

        # grid = images.image_grid(processed.images, p.batch_size, rows=1 << ((len(prompt_matrix_parts) - 1) // 2))
        # grid = images.draw_prompt_matrix(grid, p.width, p.height, prompt_matrix_parts)
        grid = images.image_grid(processed.images, p.batch_size, rows=number_of_comparisons)

        #Todo get labels to behave
        #grid = images.draw_prompt_matrix(grid, p.width, p.height, all_prompts)
        #grid = images.draw_prompt_matrix(grid, p.width, p.height, all_prompts[0:2])
        processed.images.insert(0, grid)

        #Todo: add grids to a queue so they can be rated in a separate image window
        #imagesToRate.append(grid)
        #ratingImageUI.value = imagesToRate[0]
        #processed.images.insert(1, grid)
        processed.index_of_first_image = 1
        processed.infotexts.insert(0, processed.infotexts[0])
        #processed.infotexts.insert(1, processed.infotexts[0])

        #Todo add checks to make sure an image propertly displayed

        
        state = "ready" #allows rating buttons to work

        if opts.grid_save:
            images.save_image(processed.images[0], p.outpath_grids, "prompt_matrix", extension=opts.grid_format, prompt=original_prompt, seed=processed.seed, grid=True, p=p)

        return processed
